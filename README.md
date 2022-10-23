# Rucio-SENSE Interoperation Prototype Simulation

## Southbound
Contains components that allow high-level components to communicate with low-level components
- Burro: stand-in for Rucio
```
./bin/burro
```
- [DMM](https://github.com/jkguiang/rucio-sense-dmm)

## Northbound
Contains components that allow low-level components to communicate with high-level components
- VSNet: stand-in for ESNet+FTS
```
./bin/vsnet
```
- NONSENSE: stand-in for SENSE
```
./bin/nonsense
```

## Running the simulation containers
1. Install Docker
2. Clone this repository
```
git clone git@github.com:jkguiang/rucio-sense-sim.git
```
3. Request the ESNet topology JSON from an author/maintainer or ESNet and put it in the configured location (see the VSNet section of `config.yaml`):
```
cd rucio-sense-sim
mv /path/to/esnet_adjacencies.json data/esnet_adjacencies.json
mv /path/to/esnet_coordinates.json data/esnet_coordinates.json
```
4. Spool up the containers using `docker-compose`
```
docker-compose --file etc/docker-compose.yaml up -d
```
5. Ensure that all four containers are running with `docker ps`
```
CONTAINER ID   IMAGE                            COMMAND                  CREATED         STATUS         PORTS     NAMES
7500768303db   jguiang/rucio-sense-sim:latest   "python bin/vsnet"       6 seconds ago   Up 5 seconds             etc_vsnet_1
5fc40c71cf8c   jguiang/rucio-sense-sim:latest   "tail -f /dev/null"      6 seconds ago   Up 5 seconds             etc_burro_1
8fca40160de7   jguiang/rucio-sense-sim:latest   "python bin/nonsense"    6 seconds ago   Up 5 seconds             etc_nonsense_1
c11142487fbe   jguiang/rucio-sense-sim:latest   "python bin/dmm --lo…"   6 seconds ago   Up 5 seconds             etc_dmm_1
```
6. Hop onto the `burro` container
```
docker exec -it etc_burro_1 /bin/sh
```
7. Run `burro`
```
./bin/burro --loglevel=DEBUG
```
8. (Optional) restart containers in order to run again
```
docker restart $(docker ps -q)
```
9. Clean up or restart containers
```
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker system prune -f --volumes
```

## Editing the simulation parameters
The simulation is primarily driven by the configuation YAML (`config.yaml`) found in this respository. 
This sections provides more details as to exactly what each configuration line in the YAML does. 
Importantly, the host and port for each component of the simulation is configured by an environment variable (see `setup.sh`).

### Burro
- `heartbeat (int)`: number of seconds to wait between runs of Burro's main loop
- `throttler (bool)`: whether or not to throttle the number of transfers submitted
- `rules`: list of Rucio-like "rules" to run
    - `delay (int)`: number of seconds to wait before submitting this rule
    - `src_rse (str)`: name of source site (e.g. `T2_US_SDSC`)
    - `dst_rse (str)`: name of destination site (e.g. `T2_US_Caltech_Test`)
    - `size_GB (float)`: total size of transfer
    - `n_transfers (int)`: total number of transfers
    - `priority (int)`: numerical priority of this rule (0 = no priority)
    - `src_limit (int, optional)`: maximum number of transfers that the source can support (only respected if `throttler == true`)
    - `dst_limit (int, optional)`: maximum number of transfers that the destination can support (only respected if `throttler == true`)

## Running the simulation locally
1. Clone both the Rucio-SENSE simulation and DMM
```
git clone https://github.com/jkguiang/rucio-sense-sim
git clone https://github.com/jkguiang/rucio-sense-dmm
```
2. Install the following dependencies:
```
pip install pyyaml fastapi "uvicorn[standard]" sense-o-api==1.23 python-multipart
```
3. Go to DMM base dir and copy the mock SENSE yaml to the appropriate location:
```
cd rucio-sense-dmm
cp .sense-o-auth.yaml.sim ~/sense-o-auth.yaml
```
4. Request the ESNet topology JSON from an author/maintainer or ESNet and put it in the configured location (see the VSNet section of `config.yaml`):
```
cd rucio-sense-sim
mv /path/to/esnet_adjacencies.json data/esnet_adjacencies.json
mv /path/to/esnet_coordinates.json data/esnet_coordinates.json
```
5. Open 4 terminal sessions and start each component of the simulation (in this order!)
```
# Session 1:
cd rucio-sense-sim
source setup.sh     # sets up simulation environment
./bin/vsnet         # starts VSNet
```
```
# Session 2:
cd rucio-sense-sim
source setup.sh     # sets up simulation environment
./bin/nonsense      # starts NONSENSE
```
```
# Session 3:
cd rucio-sense-dmm
source setup.sh     # sets up DMM environment
./bin/dmm           # starts DMM
```
```
# Session 4:
cd rucio-sense-sim
source setup.sh     # sets up simulation environment
./bin/burro         # starts Burro
```
