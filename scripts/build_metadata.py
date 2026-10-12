from app.config import MARKET_DB_PATH, DOCUMENTS_DIR, METADATA_DB_PATH
from metadata.database import initialize
from metadata.builders.sql_builder import SQLMetadataBuilder
from metadata.builders.file_builder import FileMetadataBuilder
from metadata.builders.enrichment import enrich

if __name__=='__main__':
    print('metadata:', initialize())
    if MARKET_DB_PATH.exists(): print('sql:', SQLMetadataBuilder(db_path=MARKET_DB_PATH).build())
    else: print('sql: skipped, not found:', MARKET_DB_PATH)
    print('files:', FileMetadataBuilder().build(DOCUMENTS_DIR))

    print('enrichment:', enrich(DOCUMENTS_DIR))
