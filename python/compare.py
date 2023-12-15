import json
import argparse

def compare(trx_id, obj, str):
    if not obj and not str:
        return True
    obj_from_str = json.loads(str)

    # Iterate through the keys in obj
    for key, value in obj.items():
        if value == "*":
            continue
        if key not in obj_from_str:
            # print("\nTrx_id %s key not found: '%s'" % (trx_id, key))
            return False
        if obj_from_str[key] != value and not (value == 'null' and obj_from_str[key] == None):
            # print("\nTrx_id %s found: '%s: %s', expected: '%s: %s'" % (trx_id, key, obj_from_str[key], key, value))
            return False

    return True

def find_action(expected_action, actions, start_index):
    for i in range(start_index, len(actions)):
        action = actions[i]['action']
        if (
            (actions[i]['trx_id'] == expected_action['trx_id'] or expected_action['trx_id'] == '*')
            and actions[i]['receiver'] == expected_action['receiver']
            and action['account'] == expected_action['account']
            and action['name'] == expected_action['action_name']
            and compare(actions[i]['trx_id'], expected_action['params'], action['jsonData'])
        ):
            return i

    return None

def find_dbop(expected_dbop, dbops, start_index):
    for i in range(start_index, len(dbops)):
        dbop = dbops[i]
        if dbop.get('trx_id') != expected_dbop.get('trx_id'): 
            continue
        if (
            dbop.get('code') == expected_dbop.get('code')
            and dbop.get('scope') == expected_dbop.get('scope')
            and dbop.get('tableName') == expected_dbop.get('table_name')
            and dbop.get('primaryKey') == expected_dbop.get('pkey')
            and compare(dbop.get('trx_id'), expected_dbop.get('fields'), dbop.get('newDataJson'))
        ):
            return i

    return None

def extract_dmlog_records(dmlog_data):
    dmlog_actions = []
    dmlog_dbops = []

    for block_record in dmlog_data:
        for transaction_trace in block_record.get('unfilteredTransactionTraces', []):
            trx_id = transaction_trace.get('id', 'n/a')
            for action_trace in transaction_trace.get('actionTraces', []):
                action_trace['trx_id'] = trx_id
                dmlog_actions.append(action_trace)
            for dbop in transaction_trace.get('dbOps', []):
                dbop['trx_id'] = trx_id
                dmlog_dbops.append(dbop)

    return dmlog_actions, dmlog_dbops


def bail(msg):
    print(msg)
    exit(1)

def main():
    parser = argparse.ArgumentParser(description='Compare firehose deep-mind JSON with expected JSONL log')
    parser.add_argument('expected_file', type=str, nargs='?', default='expected.jsonl', help='Path to expected.jsonl file')
    parser.add_argument('dmlog_file', type=str, nargs='?', default='dm.log.json', help='Path to dm.log.json file')
    args = parser.parse_args()

    expected_records = []
    with open(args.expected_file, 'r') as expected_file:
        for line in expected_file:
            expected_records.append(json.loads(line))

    with open(args.dmlog_file, 'r') as dmlog_file:
        dmlog_data = json.load(dmlog_file)

    dmlog_actions, dmlog_dbops = extract_dmlog_records(dmlog_data)

    failed = 0
    index = -1
    actions = 0
    for record in expected_records:
        trx_id = record['trx_id']
        if record['type'] == 'action':
            # print("Looking for action %s::%s in %s ... " % (record['account'], record['action_name'], trx_id), end='')
            found = find_action(record, dmlog_actions, index)
            if found == None:
                print("No action found for %s:%s @ trx %s" % (record.get('account'), record.get('action_name'), trx_id))
                failed += 1
            else: 
                index = found + 1
                actions += 1
        elif record['type'] != 'dbop':
            print("Invalid record type: %s for trx_id %s", record['type'], trx_id)

    index = -1
    db_ops = 0
    for record in expected_records:
        trx_id = record['trx_id']
        if record['type'] == 'dbop':
            found = find_dbop(record, dmlog_dbops, index)
            if found == None:
                print("No matching dbop found for table update %s:%s @ trx %s" % (record.get('code'), record.get('table_name'), trx_id))
                failed += 1
            else: 
                index = found + 1
                db_ops += 1

    if failed > 0:
        bail("🛑 Failed %d out of %d actions and db_ops - see above" % (failed, actions + db_ops))
    
    print("✅ Validated %d actions and %d db_ops successfully" % (actions, db_ops))



if __name__ == "__main__":
    main()