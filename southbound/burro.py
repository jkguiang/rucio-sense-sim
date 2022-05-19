import yaml
import json
import time
import uuid
import signal
import logging
import argparse
from multiprocessing.connection import Client
from threading import Thread, Event, Lock

class Transfer:
    def __init__(self, rule_id, src_rse, dst_rse, priority, size_GB):
        self.id = uuid.uuid4().hex
        self.rule_id = rule_id
        self.src_rse = src_rse
        self.dst_rse = dst_rse
        self.rse_pair_id = f"{src_rse}&{dst_rse}"
        self.priority = priority
        self.byte_count = size_GB*10**9
        self.state = "PREPARING"

class Rule:
    def __init__(self, rule_config):
        self.transfers = []
        self.rule_id = uuid.uuid4().hex
        self.delay = rule_config.get("delay")
        for config in rule_config.get("rule"):
            for _ in range(config.get("n_transfers")):
                new_transfer = Transfer(
                    self.rule_id,
                    config.get("src_rse"),
                    config.get("dst_rse"),
                    config.get("priority"),
                    config.get("size_GB")/config.get("n_transfers")
                )
                self.transfers.append(new_transfer)

    def get_transfers(self, state):
        return [transfer for transfer in self.transfers if transfer.state == state]

    def clean(self):
        for transfer in self.get_transfers("DELETE"):
            self.transfers.remove(transfer)

class Burro:
    def __init__(self, config_yaml):
        with open(config_yaml, "r") as f_in:
            config = yaml.safe_load(f_in)
            # Extract Burro configuration parameters
            burro_config = config.get("burro")
            self.heartbeat = burro_config.get("heartbeat", 10)
            self.use_throttler = burro_config.get("throttler", False)
            all_rules = [Rule(c) for c in burro_config.get("rules")]
            # Extract DMM configuration parameters
            dmm_config = config.get("dmm")
            dmm_host = dmm_config.get("host", "localhost")
            dmm_port = dmm_config.get("port", 5000)
            self.dmm_address = (dmm_host, dmm_port)
            with open(dmm_config.get("authkey"), "rb") as f_in:
                self.dmm_authkey = f_in.read()

        self.active_rules = []
        self.rule_stager = Thread(target=self.__stage_rules, args=(all_rules,))
        self.rule_stager.name = "StagerThread"
        self.rule_runner = Thread(target=self.__run_rules)
        self.rule_runner.name = "RunnerThread"
        self.lock = Lock()
        self.__stop_event = Event()
        self.__heart = Event()

    def start(self):
        self.rule_stager.start()
        self.rule_runner.start()

    def stop(self):
        self.__stop_event.set()
        self.__heart.set()
        self.rule_stager.join()
        self.rule_runner.join()

    def __stage_rules(self, rules):
        logging.debug(f"Starting rule stager; {len(rules)} rules to stage")
        t_start = time.time()
        remaining_rules = list(rules) # make a local copy
        while not self.__stop_event.is_set() and len(remaining_rules) > 0:
            t_now = time.time()
            rules_to_start = []
            for rule in remaining_rules:
                if (t_now - t_start) > rule.delay:
                    rules_to_start.append(rule)
            self.lock.acquire()
            for rule in rules_to_start:
                self.active_rules.append(rule)
                remaining_rules.remove(rule)
            self.lock.release()
        logging.debug(f"Stopping rule stager; no more rules to stage")

    def __run_rules(self):
        n_heartbeats = 0
        while not self.__stop_event.is_set():
            logging.debug(f"Starting heartbeat {n_heartbeats}")
            self.lock.acquire()
            for rule in self.active_rules:
                rule.clean()
            active_rules = list(self.active_rules)
            self.lock.release()
            # Collect transfers
            transfers = {
                "PREPARING": [],
                "WAITING": [],
                "QUEUED": [],
                "SUBMITTED": [],
                "DONE": []
            }
            for rule in active_rules:
                for state in transfers.keys():
                    transfers[state] += rule.get_transfers(state)
            # Print transfers
            for state, queue in transfers.items():
                logging.debug(f"{state}: {len(queue)}")
            # Process transfers
            self.preparer(transfers["PREPARING"])
            if self.use_throttler:
                self.throttler(transfers["WAITING"])
            self.submitter(transfers["QUEUED"])
            self.poller(transfers["SUBMITTED"])
            self.finisher(transfers["DONE"])
            self.__heart.wait(self.heartbeat)
            n_heartbeats += 1

    def preparer(self, transfers):
        logging.debug(f"Running preparer on {len(transfers)} transfers")
        prepared_rules = {}
        for transfer in transfers:
            if self.use_throttler:
                transfer.state = "WAITING"
            else:
                transfer.state = "QUEUED"
            # Check if rule has been accounted for
            rule_id = transfer.rule_id
            if rule_id not in prepared_rules.keys():
                prepared_rules[rule_id] = {}
            # Check if RSE pair has been accounted for
            rse_pair_id = transfer.rse_pair_id
            if rse_pair_id not in prepared_rules[rule_id].keys():
                prepared_rules[rule_id][rse_pair_id] = {
                    "transfer_ids": [],
                    "priority": transfer.priority,
                    "n_transfers_total": 0,
                    "n_bytes_total": 0
                }
            # Update request attributes
            prepared_rules[rule_id][rse_pair_id]["transfer_ids"].append(transfer.id)
            prepared_rules[rule_id][rse_pair_id]["n_transfers_total"] += 1
            prepared_rules[rule_id][rse_pair_id]["n_bytes_total"] += transfer.byte_count

        with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
            client.send(("PREPARER", prepared_rules))

    def throttler(self, transfers):
        """
        {
            This ID is NOT the rule ID (it's the RSE ID)!! Uh oh...
            '07e0195bbf764c42b9bbfa8e35daf890': {
                'rse': 'XRD3', 
                'activities': {
                    'User Subscriptions': {
                        'waiting': 6, 
                        'transfer': 0, 
                        'strategy': 'fifo', 
                        'deadline': None, 
                        'volume': None, 
                        'threshold': 1, 
                        'accounts': {
                            root: {'waiting': 6, 'transfer': 0}
                        }
                    }
                }
            }
        }
        """
        logging.debug(f"Running throttler on {len(transfers)} transfers")
        for transfer in transfers:
            transfer.state = "QUEUED"

    def submitter(self, transfers):
        logging.debug(f"Running submitter on {len(transfers)} transfers")
        # Count submissions and sort by rule id and RSE pair
        submitter_reports = {}
        for transfer in transfers:
            # Get rule ID
            rule_id = transfer.rule_id
            if rule_id not in submitter_reports.keys():
                submitter_reports[rule_id] = {}
            # Get RSE pair ID
            rse_pair_id = transfer.rse_pair_id
            if rse_pair_id not in submitter_reports[rule_id].keys():
                submitter_reports[rule_id][rse_pair_id] = {
                    "priority": transfer.priority, # attach priority in case it changed
                    "n_transfers_submitted": 0
                }
            # Count transfers
            submitter_reports[rule_id][rse_pair_id]["n_transfers_submitted"] += 1
        # Get SENSE mapping
        with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
            client.send(("SUBMITTER", submitter_reports))
            sense_map = client.recv()
        # Do SENSE link replacement
        for transfer in transfers:
            # TODO: ping PSNet about transfer submissions
            transfer.state = "SUBMITTED"

    def poller(self, transfers):
        """
        Could be one of at least two things:

            1. polls PSNet for each group (grouping TBD) of transfers
            2. runs on a separate thread, listens for pings from PSNet; PSNet sends which 
               transfers (grouping TBD) are finished

        For now, just immediately moves transfer to 'DONE'
        """
        logging.debug(f"Running poller on {len(transfers)} transfers")
        for transfer in transfers:
            transfer.state = "DONE"

    def finisher(self, all_transfers):
        logging.debug(f"Running finisher on {len(all_transfers)} transfers")
        organized_transfers = {}
        # Organize transfers by rule ID and stage them for deletion
        for transfer in all_transfers:
            rule_id = transfer.rule_id
            if rule_id not in organized_transfers.keys():
                organized_transfers[rule_id] = []
            organized_transfers[rule_id].append(transfer)
            transfer.state = "DELETE"
        # Parse organized transfers
        for rule_id, transfers in organized_transfers.items():
            finisher_reports = {}
            for transfer in transfers:
                rse_pair_id = transfer.rse_pair_id
                if rse_pair_id not in finisher_reports.keys():
                    finisher_reports[rse_pair_id] = {
                        "n_transfers_finished": 0,
                        "n_bytes_transferred": 0
                    }
                finisher_reports[rse_pair_id]["n_transfers_finished"] += 1
                finisher_reports[rse_pair_id]["n_bytes_transferred"] += transfer.byte_count

            with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
                client.send(("FINISHER", {rule_id: finisher_reports}))

def sigint_handler(burro):
    def actual_handler(sig, frame):
        logging.info("Stopping Donkey (received SIGINT)")
        burro.stop()
        sys.exit(0)
    return actual_handler

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Rucio-SENSE pseudo-Rucio client")
    cli.add_argument(
        "-c", "--config", type=str, default="config.yaml", 
        help="path to config yaml (default: ./config.yaml)"
    )
    cli.add_argument(
        "--loglevel", type=str, default="WARNING", 
        help="log level: DEBUG, INFO, WARNING (default), or ERROR"
    )
    cli.add_argument(
        "--logfile", type=str, default="burro.log", 
        help="path to log file (default: ./burro.log)"
    )
    args = cli.parse_args()

    # Set up logging handlers
    handlers = [logging.FileHandler(filename=args.logfile)]
    if args.loglevel.upper() == "DEBUG":
        handlers.append(logging.StreamHandler(sys.stdout))
    # Configure logging
    logging.basicConfig(
        format="(%(threadName)s) [%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%m-%d-%Y %H:%M:%S %p",
        level=getattr(logging, args.loglevel.upper()),
        handlers=handlers
    )
    
    # Start Burro
    burro = Burro(args.config)
    signal.signal(signal.SIGINT, sigint_handler(burro))
    logging.info("Starting Burro")
    burro.start()
