from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///mydatabase.db', echo=True)

conn = engine.connect()

conn.execute(text("CREATE TABLE IF NOT EXISTS users (name str, age int)"))

conn.commit()


from sqlalchemy.orm import Session

session = Session(engine)

session.execute(text('INSERT INTO users (name, age) VALUES ("Bhavya", 20);'),)

session.commit()
