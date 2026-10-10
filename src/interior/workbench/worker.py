"""One engine operation per isolated Python process."""
import sys
from .storage import read_json, write_json

def main():
    request=read_json(sys.argv[1])
    try:
        if request['operation'].startswith('studio.'):
            from .studio.engine import execute
            result=execute(request['project'],request['operation'],request['parameters'])
        else:
            raise ValueError('Only Studio operations are supported')
        status='completed'
        if isinstance(result,dict):
            if result.get('status') in ('fail','failed','error') or result.get('execution')=='failed' or result.get('valid') is False:
                status='failed'
            elif result.get('status')=='blocked' or result.get('readiness')=='blocked':
                status='blocked'
        # Match the public CLI's JSON-compatible representation without discarding engine fields.
        import json
        result=json.loads(json.dumps(result,ensure_ascii=False,allow_nan=False,default=str))
        packet=dict(status=status,result=result,error=None)
    except Exception as exc:
        packet=dict(status='failed',result=None,error=f'{type(exc).__name__}: {exc}')
    write_json(sys.argv[2],packet)

if __name__=='__main__':
    main()
