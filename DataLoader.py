# data_loader.py

import os
import random
from datetime import datetime
from faker import Faker
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT, GEOSPHERE

# Configuración de conexión
MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://mar22266:root@cluster0.hum2fm4.mongodb.net")
DB_NAME = "restaurant_system2"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
fake = Faker()

# Drop y creación de colecciones con validadores JSON Schema
def setup_collections():
    # Limpia si existen
    for name in ["restaurants","users","menu_items","orders","reviews"]:
        try: db.drop_collection(name)
        except: pass

    # Restaurants
    db.create_collection("restaurants", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name","location","description","categories"],
            "properties": {
                "name": {"bsonType":"string"},
                "description":{"bsonType":"string"},
                "location": {
                   "bsonType":"object",
                   "required":["type","coordinates"],
                   "properties":{
                       "type":{"enum":["Point"]},
                       "coordinates":{"bsonType":"array","items":[{"bsonType":"double"},{"bsonType":"double"}],"minItems":2,"maxItems":2}
                   }
                },
                "categories":{"bsonType":"array","items":{"bsonType":"string"}}
            }
        }
    })

    # Users
    db.create_collection("users", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["username","email","created_at"],
            "properties": {
                "username":{"bsonType":"string"},
                "email":{"bsonType":"string","pattern":"^.+@.+$"},
                "created_at":{"bsonType":"date"}
            }
        }
    })

    # Menu Items
    db.create_collection("menu_items", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["restaurant_id","name","price","tags"],
            "properties": {
                "restaurant_id":{"bsonType":"objectId"},
                "name":{"bsonType":"string"},
                "description":{"bsonType":"string"},
                "price":{"bsonType":"double"},
                "tags":{"bsonType":"array","items":{"bsonType":"string"}}
            }
        }
    })

    # Orders
    db.create_collection("orders", validator={
        "$jsonSchema": {
            "bsonType":"object",
            "required":["user_id","restaurant_id","items","status","created_at"],
            "properties":{
                "user_id":{"bsonType":"objectId"},
                "restaurant_id":{"bsonType":"objectId"},
                "items":{
                    "bsonType":"array",
                    "items":{
                        "bsonType":"object",
                        "required":["item_id","quantity","unit_price"],
                        "properties":{
                            "item_id":{"bsonType":"objectId"},
                            "quantity":{"bsonType":"int"},
                            "unit_price":{"bsonType":"double"}
                        }
                    }
                },
                "status":{"enum":["pending","completed","cancelled"]},
                "created_at":{"bsonType":"date"}
            }
        }
    })

    # Reviews
    db.create_collection("reviews", validator={
        "$jsonSchema":{
            "bsonType":"object",
            "required":["user_id","rating","comment","created_at"],
            "properties":{
                "user_id":{"bsonType":"objectId"},
                "restaurant_id":{"bsonType":"objectId"},
                "order_id":{"bsonType":"objectId"},
                "rating":{"bsonType":"int","minimum":1,"maximum":5},
                "comment":{"bsonType":"string"},
                "created_at":{"bsonType":"date"}
            }
        }
    })

# Creación de índices
def create_indexes():
    # Restaurants texto sobre name/description, geo, simple sobre _id, compuesto sobre categories+name
    db.restaurants.create_index([("name","text"),("description","text")])
    db.restaurants.create_index([("location","2dsphere")])
    db.restaurants.create_index([("categories", ASCENDING)])
    db.restaurants.create_index([("name", ASCENDING),("categories", ASCENDING)])

    # Users simple y compuesto
    db.users.create_index("email", unique=True)
    db.users.create_index([("created_at", DESCENDING),("username", ASCENDING)])

    # Menu Items multikey en tags, text en name, simple en restaurant_id
    db.menu_items.create_index([("tags", ASCENDING)])
    db.menu_items.create_index([("name","text")])
    db.menu_items.create_index("restaurant_id")

    # Orders simple en user_id, compuesto en created_at+status
    db.orders.create_index("user_id")
    db.orders.create_index([("created_at", DESCENDING),("status", ASCENDING)])

    # Reviews simple en rating, compuesto en restaurant_id+rating
    db.reviews.create_index("rating")
    db.reviews.create_index([("restaurant_id", ASCENDING),("rating", DESCENDING)])

# Generación de datos
def generate_data():
    # Restaurantes
    restaurants = []
    for _ in range(15000):
        lon = float(fake.longitude())
        lat = float(fake.latitude())
        restaurants.append({
            "name": fake.company(),
            "description": fake.text(max_nb_chars=200),
            "location": {"type": "Point", "coordinates": [lon, lat]},
            "categories": random.sample(
                ["italian","chinese","japanese","mexican","vegan","fastfood"], k=2
            )
        })
    res = db.restaurants.insert_many(restaurants)
    restaurant_ids = res.inserted_ids

    # Usuarios 
    users = []
    for i in range(10000):
        users.append({
            "username": fake.user_name(),
            "email": f"user{i}@example.com",
            "created_at": fake.date_time_between(start_date="-2y", end_date="now")
        })
    uids = db.users.insert_many(users).inserted_ids

    # Items de menu
    menu_items = []
    for _ in range(50000):
        rid = random.choice(restaurant_ids)
        menu_items.append({
            "restaurant_id": rid,
            "name": fake.word().title(),
            "description": fake.text(max_nb_chars=100),
            "price": round(random.uniform(5,50), 2),
            "tags": random.sample(
                ["spicy","gluten-free","vegan","dessert","kids"], k=2
            )
        })
    mid = db.menu_items.insert_many(menu_items).inserted_ids

    # Cachear todos los precios en memoria para acelerar las ordenes
    price_map = {
        doc["_id"]: doc["price"]
        for doc in db.menu_items.find({}, {"price": 1})
    }

    # Ordenes 
    orders = []
    for _ in range(10000):
        user_id = random.choice(uids)
        rest_id = random.choice(restaurant_ids)
        items = []
        for it in random.sample(mid, k=random.randint(2,5)):
            items.append({
                "item_id": it,
                "quantity": random.randint(1,3),
                "unit_price": price_map[it]   
            })
        orders.append({
            "user_id": user_id,
            "restaurant_id": rest_id,
            "items": items,
            "status": random.choice(["pending","completed","cancelled"]),
            "created_at": fake.date_time_between(start_date="-6m", end_date="now")
        })
    oids = db.orders.insert_many(orders).inserted_ids

    # Reseñas 
    reviews = []
    for _ in range(10000):
        reviews.append({
            "user_id": random.choice(uids),
            "restaurant_id": random.choice(restaurant_ids),
            "order_id": random.choice(oids),
            "rating": random.randint(1,5),
            "comment": fake.sentence(nb_words=12),
            "created_at": fake.date_time_between(start_date="-3m", end_date="now")
        })
    db.reviews.insert_many(reviews)

    # Conteo final
    total = sum(db[c].count_documents({}) for c in
                ["restaurants","users","menu_items","orders","reviews"])
    print(f"¡Datos cargados! Total de documentos: {total}")

if __name__ == "__main__":
    setup_collections()
    create_indexes()
    generate_data()
