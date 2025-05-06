# Restaurant Orders & Reviews API

**Breve descripción**  
API REST construida con FastAPI y MongoDB para gestionar restaurantes, usuarios, platos del menú, pedidos y reseñas.

##  Tecnologías

- **Backend**: Python 3.9+, FastAPI  
- **Base de datos**: MongoDB (Atlas)  
- **ORM ligero**: PyMongo + GridFS  
- **Validación**: Pydantic  

## Ejecutar servidor

- uvicorn main:app --reload --host 0.0.0.0 --port 8000

## Endpoints principales

### Restaurantes
- `GET    /restaurants`
- `POST   /restaurants`
- `GET    /restaurants/{id}`
- `PUT    /restaurants/{id}`
- `DELETE /restaurants/{id}`

### Usuarios
- `GET    /users`
- `POST   /users`
- `GET    /users/{id}`
- `PUT    /users/{id}`
- `DELETE /users/{id}`
- `POST   /users/batch-create`
- `DELETE /users/batch-delete`

### Platos de menú
- `GET    /menu-items`
- `POST   /menu-items`
- `GET    /menu-items/{id}`
- `PUT    /menu-items/{id}`
- `DELETE /menu-items/{id}`

### Pedidos
- `GET    /orders`
- `POST   /orders`
- `GET    /orders/{id}`
- `PUT    /orders/{id}`
- `DELETE /orders/{id}`
- `PATCH  /orders/{id}/add-item`
- `PATCH  /orders/{id}/remove-item/{item_id}`
- `PATCH  /orders/batch-update`

### Reseñas
- `GET    /reviews`
- `POST   /reviews`
- `GET    /reviews/{id}`
- `PUT    /reviews/{id}`
- `DELETE /reviews/{id}`
- `GET    /reviews/count`

### Agregaciones y utilidades
- `GET /restaurants/top-rated?limit={n}`
- `GET /menu-items/most-ordered?limit={n}`
- `GET /restaurants/distinct-categories`

### Imágenes (GridFS)
- `POST /restaurants/{id}/upload-image`
- `GET  /restaurants/{id}/image/{file_id}`
