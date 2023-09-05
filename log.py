import logging
import json


class JsonFormatter(logging.Formatter):
    def format(self, record):

        json_record = {
            # "level": record.levelname,
            "timestamp": self.formatTime(record, self.datefmt),
            "type": record.msg,
        }
        dict = record.__dict__
        if record.msg == "action":
            json_record["action_name"] = dict.get("action_name")
            json_record["account"] = dict.get("account")
            json_record["receiver"] = dict.get("receiver")
            json_record["params"] = dict.get("params")
            
        if record.msg == "dbop":
            json_record["table_name"] = dict.get("table_name")
            json_record["code"] = dict.get("code")
            json_record["scope"] = dict.get("scope")
            json_record["fields"] = dict.get("fields")
    
        return json.dumps(json_record)
    
def initLogging(filename):
    handler = logging.FileHandler(filename, mode='w')
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def logAction(account, receiver, action_name, params):
    logging.info("action", extra={"action_name": action_name, "account": account, "receiver": receiver, "params": params})
    
def logDbop(code, scope, table_name, pkey, op, fields):
    if op not in ['INS', 'UPD', 'REM']:
        raise ValueError(f"Invalid operation: {op}. Operation must be one of 'INS', 'UPD', or 'REM'")
    logging.info("dbop", extra={"code": code, "scope": scope, "table_name": table_name, "pkey": pkey, "op": op, "fields": fields})

