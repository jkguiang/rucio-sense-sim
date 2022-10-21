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

## Running the simulation
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

## Editing the simulation parameters
The simulation is primarily driven by the configuation YAML (`config.yaml`) found in this respository.
