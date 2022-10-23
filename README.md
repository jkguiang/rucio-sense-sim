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
2. Spool up the containers using `docker-compose`:
```
docker-compose --file etc/docker-compose.yaml up -d
```
3. Ensure that all four containers are running with `docker ps`
```
CONTAINER ID   IMAGE                            COMMAND                  CREATED         STATUS         PORTS     NAMES
7500768303db   jguiang/rucio-sense-sim:latest   "python bin/vsnet"       6 seconds ago   Up 5 seconds             etc_vsnet_1
5fc40c71cf8c   jguiang/rucio-sense-sim:latest   "tail -f /dev/null"      6 seconds ago   Up 5 seconds             etc_burro_1
8fca40160de7   jguiang/rucio-sense-sim:latest   "python bin/nonsense"    6 seconds ago   Up 5 seconds             etc_nonsense_1
c11142487fbe   jguiang/rucio-sense-sim:latest   "python bin/dmm --lo…"   6 seconds ago   Up 5 seconds             etc_dmm_1
```
3. Hop onto the `burro` container:
```
docker exec -it etc_burro_1 /bin/sh
```
4. Run `burro`:
```
./bin/burro --loglevel=DEBUG
```
5. (Optional) restart containers in order to run again
```
docker restart $(docker ps -q)
```
6. Clean up or restart containers
```
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker system prune -f --volumes
```

## Editing the simulation parameters
The simulation is primarily driven by the configuation YAML (`config.yaml`) found in this respository.

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
6. Go to simulation base dir and run the following commands
```
# Session 1:
source setup.sh     # sets up simulation environment
./bin/vsnet         # starts VSNet
# Session 2:
source setup.sh     # sets up simulation environment
./bin/nonsense      # starts NONSENSE
```
7. Go to DMM base dir and run
```
# Session 3:
source setup.sh     # sets up DMM environment
./bin/dmm           # starts DMM
```
8. Go to simulation base dir and run
```
# Session 4:
source setup.sh     # sets up simulation environment
./bin/burro         # starts Burro
```
