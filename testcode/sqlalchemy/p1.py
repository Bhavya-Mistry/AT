from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///mydatabase.db', echo=True)

conn = engine.connect()

conn.execute(text("CREATE TABLE IF NOT EXISTS users (name str, age int)"))

conn.commit()