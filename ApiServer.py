import os
import io
import gridfs
from datetime import datetime
from bson import ObjectId
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from fastapi import Body
from gridfs.errors import NoFile
from fastapi.responses import Response
from bson import ObjectId

# Configuración
MONGO_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://mar22266:root@cluster0.hum2fm4.mongodb.net"
)
DB_NAME = "restaurant_system2"

# Cliente MongoDB
sync_client = MongoClient(MONGO_URI)
db = sync_client[DB_NAME]
fs = gridfs.GridFS(db)

app = FastAPI(title="Restaurant Orders & Reviews API")

# Helper para ObjectId
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, *args, **kwargs):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

# Modelos Pydantic
# Clases de modelo para las colecciones
class Restaurant(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: str
    location: dict
    categories: List[str]

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    username: str
    email: EmailStr
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

class MenuItem(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    restaurant_id: PyObjectId
    name: str
    description: Optional[str]
    price: float
    tags: List[str]

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class OrderItem(BaseModel):
    item_id: PyObjectId
    quantity: int
    unit_price: float

    class Config:
        json_encoders = {ObjectId: str}

class Order(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    restaurant_id: PyObjectId
    items: List[OrderItem]
    status: str
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

class Review(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    restaurant_id: Optional[PyObjectId]
    order_id: Optional[PyObjectId]
    rating: int
    comment: str
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# Utilidad para proyecciones
def parse_fields(fields: Optional[str]):
    if not fields:
        return None
    return {f: 1 for f in fields.split(",")}

def serialize_doc(doc):
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized

def serialize_list(docs):
    return [serialize_doc(doc) for doc in docs]

# Agregaciones
@app.get("/restaurants/top-rated")
def top_rated(limit: int = 10):
    pipeline = [
        {"$group": {
            "_id": "$restaurant_id",
            "avgRating": {"$avg": "$rating"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"avgRating": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "restaurants",           
            "localField": "_id",              
            "foreignField": "_id",           
            "as": "restaurant_info"           
        }},
        {"$unwind": "$restaurant_info"},       
        {"$project": {
            "avgRating": 1,
            "count": 1,
            "name": "$restaurant_info.name",
            "description": "$restaurant_info.description",
            "location": "$restaurant_info.location",
            "categories": "$restaurant_info.categories"
        }}
    ]
    results = list(db.reviews.aggregate(pipeline))
    return serialize_list(results)

@app.get("/menu-items/most-ordered")
def most_ordered(limit: int = 10):
    pipeline = [
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.item_id",
            "totalQty": {"$sum": "$items.quantity"}
        }},
        {"$sort": {"totalQty": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "menu_items",           
            "localField": "_id",            
            "foreignField": "_id",           
            "as": "item_info"
        }},
        {"$unwind": "$item_info"},
        {"$project": {
            "totalQty": 1,
            "name": "$item_info.name",
            "description": "$item_info.description",
            "price": "$item_info.price",
            "tags": "$item_info.tags",
            "restaurant_id": "$item_info.restaurant_id"
        }}
    ]
    results = list(db.orders.aggregate(pipeline))
    return serialize_list(results)

@app.get("/reviews/count")
def count_reviews():
    return {"total_reviews": db.reviews.count_documents({})}

@app.get("/restaurants/distinct-categories")
def distinct_categories():
    categories = db.restaurants.distinct("categories")
    return {"distinct_categories": categories}

# Cruds de VARIOS 
@app.post("/users/batch-create", response_model=List[User], status_code=201)
def batch_create_users(users: List[User]):
    payload = [u.dict(by_alias=True, exclude={"id", "created_at"}) for u in users]
    for p in payload:
        p["created_at"] = datetime.utcnow()
    res = db.users.insert_many(payload)
    docs = list(db.users.find({"_id": {"$in": res.inserted_ids}}))
    return [User(**doc) for doc in docs]

@app.patch("/orders/batch-update")
def batch_update_orders_by_ids(
    order_ids: List[str] = Body(..., example=["680fc08…","680fc08…"]),
    new_status: str = Body(..., example="completed")
):
    obj_ids = [ObjectId(oid) for oid in order_ids]
    result = db.orders.update_many(
        {"_id": {"$in": obj_ids}},
        {"$set": {"status": new_status}}
    )
    return {
        "matched": result.matched_count,
        "modified": result.modified_count
    }

@app.delete("/users/batch-delete")
def batch_delete_users(user_ids: List[str] = Body(...)):
    # Convierte cada string a ObjectId
    obj_ids = [ObjectId(uid) for uid in user_ids]
    result = db.users.delete_many({"_id": {"$in": obj_ids}})
    return {"deleted_count": result.deleted_count}
# Root
@app.get("/")
def root():
    return {"message": "API up and running."}

# CRUD Restaurants
@app.get("/restaurants", response_model=List[Restaurant])
def list_restaurants(
    sort_by: str = Query("name"), order: int = Query(1),
    fields: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    proj = parse_fields(fields)
    cursor = db.restaurants.find({}, proj)\
        .sort(sort_by, order).skip(skip).limit(limit)
    return [Restaurant(**doc) for doc in cursor]

@app.post("/restaurants", response_model=Restaurant, status_code=201)
def create_restaurant(rest: Restaurant):
    payload = rest.dict(by_alias=True, exclude={"id"})
    res = db.restaurants.insert_one(payload)
    doc = db.restaurants.find_one({"_id": res.inserted_id})
    return Restaurant(**doc)

@app.get("/restaurants/{rid}", response_model=Restaurant)
def get_restaurant(rid: str):
    doc = db.restaurants.find_one({"_id": ObjectId(rid)})
    if not doc:
        raise HTTPException(404, "Restaurant not found")
    return Restaurant(**doc)

@app.put("/restaurants/{rid}", response_model=Restaurant)
def update_restaurant(rid: str, rest: Restaurant):
    payload = rest.dict(by_alias=True, exclude={"id"})
    db.restaurants.update_one(
        {"_id": ObjectId(rid)},
        {"$set": payload}
    )
    doc = db.restaurants.find_one({"_id": ObjectId(rid)})
    return Restaurant(**doc)

@app.delete("/restaurants/{rid}", response_model=None)
def delete_restaurant(rid: str):
    result = db.restaurants.delete_one({"_id": ObjectId(rid)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Restaurant not found")
    return JSONResponse(status_code=200, content={"message": "Deleted successfully"})


# CRUD Users
@app.get("/users", response_model=List[User])
def list_users(
    sort_by: str = Query("created_at"), order: int = Query(-1),
    fields: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    proj = parse_fields(fields)
    cursor = db.users.find({}, proj)\
        .sort(sort_by, order).skip(skip).limit(limit)
    return [User(**u) for u in cursor]

@app.post("/users", response_model=User, status_code=201)
def create_user(user: User):
    payload = user.dict(by_alias=True, exclude={"id", "created_at"})
    payload["created_at"] = datetime.utcnow()
    try:
        res = db.users.insert_one(payload)
    except DuplicateKeyError:
        existing = db.users.find_one({"email": payload["email"]})
        return User(**existing)
    doc = db.users.find_one({"_id": res.inserted_id})
    return User(**doc)

@app.get("/users/{uid}", response_model=User)
def get_user(uid: str):
    doc = db.users.find_one({"_id": ObjectId(uid)})
    if not doc:
        raise HTTPException(404, "User not found")
    return User(**doc)

@app.put("/users/{uid}", response_model=User)
def update_user(uid: str, user: User):
    payload = user.dict(by_alias=True, exclude={"id", "created_at"})
    db.users.update_one(
        {"_id": ObjectId(uid)},
        {"$set": payload}
    )
    doc = db.users.find_one({"_id": ObjectId(uid)})
    return User(**doc)

@app.delete("/users/{uid}", response_model=None)
def delete_user(uid: str):
    result = db.users.delete_one({"_id": ObjectId(uid)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse(status_code=200, content={"message": "Deleted successfully"})

# CRUD MenuItems
@app.get("/menu-items", response_model=List[MenuItem])
def list_menu_items(
    sort_by: str = Query("name"), order: int = Query(1),
    fields: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    proj = parse_fields(fields)
    cursor = db.menu_items.find({}, proj)\
        .sort(sort_by, order).skip(skip).limit(limit)
    return [MenuItem(**m) for m in cursor]

@app.post("/menu-items", response_model=MenuItem, status_code=201)
def create_menu_item(item: MenuItem):
    payload = item.dict(by_alias=True, exclude={"id"})
    res = db.menu_items.insert_one(payload)
    doc = db.menu_items.find_one({"_id": res.inserted_id})
    return MenuItem(**doc)

@app.get("/menu-items/{mid}", response_model=MenuItem)
def get_menu_item(mid: str):
    doc = db.menu_items.find_one({"_id": ObjectId(mid)})
    if not doc:
        raise HTTPException(404, "MenuItem not found")
    return MenuItem(**doc)

@app.put("/menu-items/{mid}", response_model=MenuItem)
def update_menu_item(mid: str, item: MenuItem):
    payload = item.dict(by_alias=True, exclude={"id"})
    db.menu_items.update_one(
        {"_id": ObjectId(mid)},
        {"$set": payload}
    )
    doc = db.menu_items.find_one({"_id": ObjectId(mid)})
    return MenuItem(**doc)

@app.delete("/menu-items/{mid}", response_model=None)
def delete_menu_item(mid: str):
    result = db.menu_items.delete_one({"_id": ObjectId(mid)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return JSONResponse(status_code=200, content={"message": "Deleted successfully"})

# CRUD Orders
@app.get("/orders", response_model=List[Order])
def list_orders(
    sort_by: str = Query("created_at"), order: int = Query(-1),
    fields: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    proj = parse_fields(fields)
    cursor = db.orders.find({}, proj)\
        .sort(sort_by, order).skip(skip).limit(limit)
    return [Order(**o) for o in cursor]

@app.post("/orders", response_model=Order, status_code=201)
def create_order(order: Order):
    payload = order.dict(by_alias=True, exclude={"id", "created_at"})
    payload["created_at"] = datetime.utcnow()
    res = db.orders.insert_one(payload)
    doc = db.orders.find_one({"_id": res.inserted_id})
    return Order(**doc)

@app.get("/orders/{oid}", response_model=Order)
def get_order(oid: str):
    doc = db.orders.find_one({"_id": ObjectId(oid)})
    if not doc:
        raise HTTPException(404, "Order not found")
    return Order(**doc)

@app.put("/orders/{oid}", response_model=Order)
def update_order(oid: str, order: Order):
    payload = order.dict(by_alias=True, exclude={"id", "created_at"})
    db.orders.update_one(
        {"_id": ObjectId(oid)},
        {"$set": payload}
    )
    doc = db.orders.find_one({"_id": ObjectId(oid)})
    return Order(**doc)

@app.delete("/orders/{oid}", response_model=None)
def delete_order(oid: str):
    result = db.orders.delete_one({"_id": ObjectId(oid)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return JSONResponse(status_code=200, content={"message": "Deleted successfully"})

# CRUD Reviews
@app.get("/reviews", response_model=List[Review])
def list_reviews(
    sort_by: str = Query("created_at"), order: int = Query(-1),
    fields: Optional[str] = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    proj = parse_fields(fields)
    cursor = db.reviews.find({}, proj)\
        .sort(sort_by, order).skip(skip).limit(limit)
    return [Review(**r) for r in cursor]

@app.post("/reviews", response_model=Review, status_code=201)
def create_review(review: Review):
    payload = review.dict(by_alias=True, exclude={"id", "created_at"})
    payload["created_at"] = datetime.utcnow()
    res = db.reviews.insert_one(payload)
    doc = db.reviews.find_one({"_id": res.inserted_id})
    return Review(**doc)

@app.get("/reviews/{rid}", response_model=Review)
def get_review(rid: str):
    doc = db.reviews.find_one({"_id": ObjectId(rid)})
    if not doc:
        raise HTTPException(404, "Review not found")
    return Review(**doc)

@app.put("/reviews/{rid}", response_model=Review)
def update_review(rid: str, review: Review):
    payload = review.dict(by_alias=True, exclude={"id", "created_at"})
    db.reviews.update_one(
        {"_id": ObjectId(rid)},
        {"$set": payload}
    )
    doc = db.reviews.find_one({"_id": ObjectId(rid)})
    return Review(**doc)

@app.delete("/reviews/{rid}", response_model=None)
def delete_review(rid: str):
    result = db.reviews.delete_one({"_id": ObjectId(rid)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return JSONResponse(status_code=200, content={"message": "Deleted successfully"})

# push y pull
@app.patch("/orders/{oid}/add-item", response_model=None)
def add_item_to_order(oid: str, item: OrderItem = Body(...)):
    result = db.orders.update_one(
        {"_id": ObjectId(oid)},
        {"$push": {"items": item.dict()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Order not found")
    return JSONResponse(status_code=200, content={"message": "Item added to order successfully"})

@app.patch("/orders/{oid}/remove-item/{item_id}", response_model=None)
def remove_item_from_order(oid: str, item_id: str):
    result = db.orders.update_one(
        {"_id": ObjectId(oid)},
        {"$pull": {"items": {"item_id": ObjectId(item_id)}}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Order not found")
    return JSONResponse(status_code=200, content={"message": "Item removed from order successfully"})

# GridFS subir y descargar archivos
@app.post("/restaurants/{rid}/upload-image")
async def upload_image(rid: str, file: UploadFile = File(...)):
    data = await file.read()
    file_id = fs.put(
        data,
        filename=file.filename,
        contentType=file.content_type,
        metadata={"restaurant_id": ObjectId(rid)}
    )
    return {"file_id": str(file_id)}

@app.get("/restaurants/{rid}/image/{file_id}")
def get_image(rid: str, file_id: str):
    try:
        grid_out = fs.get(ObjectId(file_id))
    except NoFile:
        raise HTTPException(status_code=404, detail="Image not found")

    meta = getattr(grid_out, "metadata", {}) or {}
    if meta.get("restaurant_id") != ObjectId(rid):
        raise HTTPException(status_code=404, detail="Image not found for this restaurant")

    data = grid_out.read()
    return Response(
        content=data,
        media_type=grid_out.contentType,
        headers={"Content-Length": str(len(data)),
                 "Content-Disposition": f"inline; filename={grid_out.filename}"}
    )
    
