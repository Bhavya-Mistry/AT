from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, insert

engine = create_engine("sqlite:///mydatabase.db", echo=True)

meta = MetaData()

people = Table(
    "people",
    meta,
    Column('Id', Integer, primary_key=True),
    Column('Name', String, nullable=False),
    Column('Age', Integer)
)

meta.create_all(engine)


conn = engine.connect()

# one way

# insert_stat = people.insert().values(Name='Bhavya', Age=20)

# result = conn.execute(insert_stat)

# conn.commit()

# # 2nd way

# insert_stat = insert(people).values(Name='Bhavya1', Age=21)

# result = conn.execute(insert_stat)

# conn.commit()

# lets select data


# select_stat = people.select()

# result = conn.execute(select_stat)

# print(result)
# # for row in result.fetchall():
# #     print(row)


update_stat = people.update().where(people.c.Name == 'Bhavya1').values(Age=50)

result = conn.execute(update_stat)