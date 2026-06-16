from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta

from app.API_PROJECT.database import SessionLocal, engine
from app.API_PROJECT import models
from app.chord_prog import keys
import time
app = FastAPI()
SECRET_KEY = "anythingido"
ALGORITHM = "HS256"
models.Base.metadata.create_all(bind=engine)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------- DATABASE ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- JWT ----------------

def create_token(data: dict):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(minutes=30)

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload.get("username")
        user_id = payload.get("user_id")

        if username is None or user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        user = db.query(models.Users).filter(
            models.Users.id == user_id
        ).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        return {
            "user_id": user.id,
            "username": user.username
        }

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


# ---------------- PASSWORD ----------------

def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
):
    return pwd_context.verify(
        plain_password,
        hashed_password
    )


# ---------------- SCHEMAS ----------------

class Value(BaseModel):
    title: str
    progression: str
    previous_key: str
    present_key: str


class Register(BaseModel):
    username: str
    password: str

class Post(BaseModel):
    Caption: str
    Post: str


# ---------------- ROUTES ----------------
visitors = 0
@app.middleware("http")
async def response_load(request, call_next):
    start = time.time()
    response = await call_next(request)
    end = time.time()
    duration = end-start
    print(f"Reloading the website took {duration:.4f} seconds")
    return response

@app.middleware("http")
async def visit_load(request, call_wait):
    global visitors
    visitors+=1
    response = await call_wait(request)
    print(f"Client using this website: {visitors}")
    return response

@app.post("/register")
def register_user(
    data: Register,
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.Users).filter(
        models.Users.username == data.username
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    hashed_pw = hash_password(data.password)

    user = models.Users(
        username=data.username,
        password=hashed_pw
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "user_id": user.id,
        "username": user.username,
        "message": "User created successfully"
    }


@app.post("/login")
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.Users).filter(
        models.Users.username == form_data.username
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if not verify_password(
        form_data.password,
        user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect password"
        )

    token = create_token({
        "user_id": user.id,
        "username": user.username
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.post("/convert-key")
def convert_key(
    data: Value,
    current_user: dict = Depends(get_current_user)
):
    if data.present_key not in keys:
        raise HTTPException(
            status_code=400,
            detail="Invalid key"
        )

    progression = data.progression.split()

    new_chords = []

    for roman in progression:
        result = keys[data.present_key].get(roman)
        new_chords.append(
            result if result else "unknown"
        )

    return {
        "title": data.title,
        "result": new_chords,
        "user": current_user["username"],
        "message": "success"
    }


# only signed in user can use this route
@app.post("/post-blogs")
def post_blogs(data: Post,
            db: Session = Depends(get_db),
            blog_user: dict = Depends(get_current_user)):
    post_user = models.Users2(
        username = blog_user["username"],      
        Caption = data.Caption,
        Post = data.Post       
    )
    db.add(post_user)
    db.commit()
    db.refresh(post_user)
    return {"message":"Successfully Created!",
            "blog_owner":post_user.username}

@app.get("/show-blogs")
def show_blogs(db: Session = Depends(get_db), blog_user: dict = Depends(get_current_user)):
    all_blogs = db.query(models.Users2).all()
    return all_blogs
    
@app.get("/show-blogsid/{post_id}")
def show_blogs_id(post_id: int, db:Session = Depends(get_db)):
    specific_id = db.query(models.Users2).filter(models.Users2.id== post_id).first()
    if not specific_id:
        raise HTTPException(status_code=404, detail="Post not found, please input another valid ID.")
    specific_id.views+=1
    db.commit()
    db.refresh(specific_id)
    return specific_id    

