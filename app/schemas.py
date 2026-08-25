from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    avatar_color: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    emoji: str = "◉"
    description: str | None = None

class MemberAdd(BaseModel):
    email: EmailStr

class ExpenseCreate(BaseModel):
    group_id: int
    title: str = Field(min_length=2, max_length=160)
    amount: Decimal = Field(gt=0)
    category: str = "Other"
    split_type: str = "equal"
    notes: str | None = None

class SettlementCreate(BaseModel):
    group_id: int
    to_user_id: int
    amount: Decimal = Field(gt=0)
    note: str | None = None
