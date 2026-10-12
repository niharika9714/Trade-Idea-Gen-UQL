import json
from metadata.catalog import MetadataCatalog
if __name__=='__main__': print(json.dumps(MetadataCatalog().snapshot(),indent=2,default=str))
