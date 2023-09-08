# leap-boot

## Prerequsites
* Ubuntu 20.04/22.04
* Leap with cleos
* Python 

## Booting
* Install dependencies 
```bash
$ pip install -r requirements.txt
```
* Run `./boot.sh` - this will boot the nodes, set system contracts, run test actions, etc. Also the script will generate two log files:
    * `dm.log` - deep-mind log for the entire boot/test sequence,
    * `actions.log` - log of expected actions and dbops

## Validation (TODO)
* Run `firehose-antelope` in strict mode to decode `dm.log` and dump the resulting blocks into `dm.log.json`
* Run script that extracts actions/dbops from decoded blocks and compares them with expected actions/dbops from `actions.log.jsonl`