import sqlite3
import pandas as pd
import os
import uuid

def to_csv():
    db = sqlite3.connect('test.db')
    cursor = db.cursor()

    # Get all table names from the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for table_name in tables:
        table_name = table_name[0]

        # Read the table into a pandas DataFrame
        table = pd.read_sql_query(f"SELECT * FROM {table_name}", db)

        # Check each column for UUID data (BLOB) and convert it to string
        for column in table.columns:
            # If the column contains UUIDs (binary format), convert to string
            if table[column].dtype == 'object':  # assuming UUIDs are stored as binary BLOBs or strings
                table[column] = table[column].apply(lambda x: str(uuid.UUID(bytes=x)) if isinstance(x, bytes) else x)

        # Save the DataFrame to CSV, with the index column labeled as 'index'
        table.to_csv(f"db_dump/{table_name}.csv", index_label='index')

    cursor.close()
    db.close()

if __name__ == "__main__":
    os.makedirs('db_dump', exist_ok=True) 
    to_csv()



    
        # for (columnName, columnData) in table.iteritems():
        #     tstdf = table.loc[table[columnName].apply(type)  == uuid.UUID]
        #     if len(tstdf) > 0:
        #         print('Column Name : ', columnName)
        #         table[columnName] = table[columnName].apply(lambda x: str(x))