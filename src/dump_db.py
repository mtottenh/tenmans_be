import sqlite3
import pandas as pd
import os


def to_csv():
    db = sqlite3.connect('test.db')
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table_name in tables:
        table_name = table_name[0]
        table = pd.read_sql_query("SELECT * from %s" % table_name, db)
        table.to_csv("db_dump/" + table_name + '.csv', index_label='index')
    cursor.close()
    db.close()

if __name__ == "__main__":
    os.makedirs('db_dump', exist_ok=True) 
    to_csv()