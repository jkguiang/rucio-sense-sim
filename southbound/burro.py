import yaml
import time
import uuid
import logging
import requests
from multiprocessing.connection import Client
from threading import Thread, Event, Lock

with open("config.yaml", "r") as f_in:
    psnet_config = yaml.safe_load(f_in).get("psnet", {})

time_dilation = psnet_config.get("time_dilation", 1.0)

def now():
    return time_dilation*(time.time_ns()/10**9)

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
        with open(config_yaml, "r") as config_yaml:
            config = yaml.safe_load(config_yaml)
            # Extract Burro configuration parameters
            burro_config = config.get("burro")
            self.heartbeat = burro_config.get("heartbeat", 10)
            self.use_throttler = burro_config.get("throttler", False)
            all_rules = [Rule(c) for c in burro_config.get("rules")]
            # Extract DMM configuration parameters
            dmm_config = config.get("dmm")
            self.dmm_address = (dmm_config.get("host"), dmm_config.get("port"))
            with open(dmm_config.get("authkey"), "rb") as f_in:
                self.dmm_authkey = f_in.read()
            # Extract PSNet configuration parameters
            psnet_config = config.get("psnet")
            self.psnet_address = f"{psnet_config.get('host')}:{psnet_config.get('port')}"

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
        t_start = now()
        remaining_rules = list(rules) # make a local copy
        while not self.__stop_event.is_set() and len(remaining_rules) > 0:
            t_now = now()
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

        # Send prepared rules to DMM
        with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
            client.send(("PREPARER", prepared_rules))

        # Send prepared rules to PSNet
        for rule_id, rule_data in prepared_rules.items():
            for rse_pair_id, transfer_data in rule_data.items():
                src, dst = rse_pair_id.split("&")
                requests.post(
                    "http://localhost:9000/connections", 
                    params={
                        "burro_id": rule_id, 
                        "src": src, 
                        "dst": dst, 
                        "total_data": transfer_data["n_bytes_total"]
                    }
                )

    def throttler(self, transfers):
        """
        TODO: finish this!
        - Check each site
            - each site should track # active transfers, # max
        - Submit (# max) - (# active) transfers
        """
        logging.debug(f"Running throttler on {len(transfers)} transfers")
        for transfer in transfers:
            transfer.state = "QUEUED"

    def submitter(self, transfers):
        logging.debug(f"Running submitter on {len(transfers)} transfers")
        # Count submissions and sort by rule id and RSE pair
        connection_ids = set()
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

            connection_ids.add(f"{rule_id}_{transfer.src_rse}_{transfer.dst_rse}")
            transfer.state = "SUBMITTED"

        # Get SENSE mapping
        with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
            client.send(("SUBMITTER", submitter_reports))
            sense_map = client.recv()

        # Do SENSE link replacement
        for connection_id in connection_ids:
            requests.put(
                f"http://{self.psnet_address}/connections/{connection_id}/start"
            )

    def poller(self, unsorted_transfers):
        logging.debug(f"Running poller on {len(unsorted_transfers)} transfers")
        # Sort transfers by PSNet Connection ID
        sorted_transfers = {}
        for transfer in unsorted_transfers:
            connection_id = f"{transfer.rule_id}_{transfer.src_rse}_{transfer.dst_rse}"
            if connection_id not in sorted_transfers.keys():
                sorted_transfers[connection_id] = []

            sorted_transfers[connection_id].append(transfer)

        # Parse sorted transfers
        for connection_id, transfers in sorted_transfers.items():
            response = requests.get(
                f"http://{self.psnet_address}/connections/{connection_id}/check"
            )
            connection_data = response.json()
            if connection_data.get("is_finished", False):
                for transfer in transfers:
                    transfer.state = "DONE"
            else:
                remaining_time = connection_data.get("remaining_time", None)
                logging.debug(
                    f"{connection_id} not yet finished; {remaining_time} left"
                )

    def finisher(self, unsorted_transfers):
        logging.debug(f"Running finisher on {len(unsorted_transfers)} transfers")
        # Sort transfers by rule ID (because Rucio does) and stage them for deletion
        sorted_transfers = {}
        for transfer in unsorted_transfers:
            rule_id = transfer.rule_id
            if rule_id not in sorted_transfers.keys():
                sorted_transfers[rule_id] = []
            sorted_transfers[rule_id].append(transfer)
            transfer.state = "DELETE"

        # Parse sorted transfers
        for rule_id, transfers in sorted_transfers.items():
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
