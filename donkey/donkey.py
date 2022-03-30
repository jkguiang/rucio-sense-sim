import time
import uuid
import yaml
from multiprocessing.connection import Client
from threading import Thread, Event, Lock

class Transfer:
    def __init__(self, rule_id, src_rse, dst_rse, priority, size_GB):
        self.id = uuid.uuid4()
        self.rule_id = rule_id
        self.src_rse = src_rse
        self.dst_rse = dst_rse
        self.rse_pair_id = f"{src_rse}&{dst_rse}"
        self.priority = priority
        self.byte_count = size_GB*10**9
        self.state = "WAITING"

class Workflow:
    def __init__(self, workflow_yaml):
        self.transfers = []
        with open(workflow_yaml, "r") as f_in:
            config = yaml.safe_load(f_in)
            self.start_delay = config.get("start_delay")
            for rule_config in config.get("rules"):
                new_rule_id = uuid.uuid4()
                for _ in range(rule_config.get("n_transfers")):
                    new_transfer = Transfer(
                        new_rule_id,
                        rule_config.get("src_rse"),
                        rule_config.get("dst_rse"),
                        rule_config.get("priority"),
                        rule_config.get("size_GB")
                    )
                    self.transfers.append(new_transfer)

    def get_transfers(self, state):
        return [transfer for transfer in self.transfers if transfer.state == state]

    def clean(self):
        for transfer in self.get_transfers("DONE"):
            self.transfers.remove(transfer)

class Donkey:
    def __init__(self, workflow_yamls, heartbeat=10):
        self.heartbeat = heartbeat
        self.dmm_address = ("localhost", 5000)
        self.dmm_authkey = b"secret password"
        all_workflows = [Workflow(y) for y in workflow_yamls]
        self.active_workflows = []
        self.workflow_stager = Thread(target=self.__stage_workflows, args=(all_workflows,))
        self.workflow_runner = Thread(target=self.__run_workflows)
        self.lock = Lock()
        self.__stop_event = Event()

    def start(self):
        self.workflow_stager.start()
        self.workflow_runner.start()

    def stop(self):
        self.__stop_event.set()
        self.workflow_stager.join()
        self.workflow_runner.join()

    def __stage_workflows(self, workflows):
        t_start = time.time()
        remaining_workflows = list(workflows) # make a local copy
        while not self.__stop_event.is_set() and len(remaining_workflows) > 0:
            t_now = time.time()
            workflows_to_start = []
            for workflow in remaining_workflows:
                if (t_now - t_start) > workflow.start_delay:
                    workflows_to_start.append(workflow)
            self.lock.acquire()
            for workflow in workflows_to_start:
                self.active_workflows.append(workflow)
                remaining_workflows.remove(workflow)
            self.lock.release()

    def __run_workflows(self):
        while not self.__stop_event.is_set():
            self.lock.acquire()
            for workflow in self.active_workflows:
                workflow.clean()
            active_workflows = list(self.active_workflows)
            self.lock.release()
            # Assemble transfers
            transfers = {
                "WAITING": [],
                "QUEUED": [],
                "SUBMITTED": [],
                "DONE": []
            }
            for workflow in active_workflows:
                for state in transfers.keys():
                    transfers[state] += workflow.get_transfers(state)
            # Process transfers
            self.preparer(transfers["WAITING"])
            self.submitter(transfers["QUEUED"])
            self.poller(transfers["SUBMITTED"])
            self.finisher(transfers["DONE"])
            time.sleep(self.heartbeat)

    def preparer(self, transfers):
        prepared_rules = {}
        for transfer in transfers:
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

    def submitter(self, transfers):
        # Count submissions and sort by rule id and RSE pair
        submitter_reports = {}
        for transfer in transfers:
            rule_id = transfer.rule_id
            if rule_id not in submitter_reports.keys():
                submitter_reports[rule_id] = {}
            rse_pair_id = transfer.rse_pair_id
            if rse_pair_id not in submitter_reports[rule_id].keys():
                submitter_reports[rule_id][rse_pair_id] = 0
            submitter_reports[rule_id][rse_pair_id] += 1
        # Do SENSE link replacement
        for transfer in transfers:
            with Client(self.dmm_address, authkey=self.dmm_authkey) as client:
                submitter_report = {
                    "rule_id": transfer.rule_id,
                    "rse_pair_id": transfer.rse_pair_id,
                    "n_transfers_submitted": submitter_reports[rule_id][rse_pair_id]
                }
                client.send(("SUBMITTER", submitter_report))
                response = client.recv()

            transfer.state = "SUBMITTED"

    def poller(self, transfers):
        """
        Could be one of at least two things:

            1. polls PSNet for each group (grouping TBD) of transfers
            2. runs on a separate thread, listens for pings from PSNet; PSNet sends which 
               transfers (grouping TBD) are finished

        For now, just immediately moves transfer to 'DONE'
        """
        for transfer in transfers:
            transfer.state = "DONE"

    def finisher(self, all_transfers):
        organized_transfers = {}
        # Organize transfers by rule ID
        for transfer in all_transfers:
            rule_id = transfer.rule_id
            if rule_id not in organized_transfers.keys():
                organized_transfers[rule_id] = []
            organized_transfers[rule_id].append(transfer)
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

if __name__ == "__main__":
    donkey = Donkey(["workflows/example.yaml"])
    donkey.start()
