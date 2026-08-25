from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from .auth import create_token, get_current_user, hash_password, verify_password
from .db import Base, engine, get_db
from .models import Expense, ExpenseShare, Group, GroupMember, Settlement, User
from .schemas import ExpenseCreate, GroupCreate, LoginRequest, MemberAdd, SettlementCreate, Token, UserCreate

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Financepeer", version="1.0.0", description="Shared finance and expense splitting API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def user_payload(user: User):
    return {"id": user.id, "name": user.name, "email": user.email, "avatar_color": user.avatar_color}


def require_member(group_id: int, user: User, db: Session):
    member = db.scalar(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user.id))
    if not member:
        raise HTTPException(403, "You are not a member of this group")
    return member


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "financepeer"}


@app.post("/api/auth/register", response_model=Token)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=data.name, email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user.id), "user": user_payload(user)}


@app.post("/api/auth/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": create_token(user.id), "user": user_payload(user)}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


@app.get("/api/groups")
def groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.scalars(select(GroupMember).options(joinedload(GroupMember.group)).where(GroupMember.user_id == user.id)).all()
    return [{"id": m.group.id, "name": m.group.name, "emoji": m.group.emoji, "description": m.group.description, "member_count": len(m.group.members)} for m in memberships]


@app.post("/api/groups")
def create_group(data: GroupCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = Group(name=data.name, emoji=data.emoji, description=data.description)
    db.add(group); db.flush(); db.add(GroupMember(group_id=group.id, user_id=user.id, role="admin")); db.commit(); db.refresh(group)
    return {"id": group.id, "name": group.name, "emoji": group.emoji, "description": group.description, "member_count": 1}


@app.post("/api/groups/{group_id}/members")
def add_member(group_id: int, data: MemberAdd, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_member(group_id, user, db)
    invitee = db.scalar(select(User).where(User.email == data.email.lower()))
    if not invitee: raise HTTPException(404, "No Financepeer user found with that email")
    if db.scalar(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == invitee.id)): raise HTTPException(409, "User is already in this group")
    db.add(GroupMember(group_id=group_id, user_id=invitee.id)); db.commit()
    return {"message": f"{invitee.name} joined the group"}


@app.get("/api/groups/{group_id}/members")
def members(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_member(group_id, user, db)
    rows = db.scalars(select(GroupMember).options(joinedload(GroupMember.user)).where(GroupMember.group_id == group_id)).all()
    return [{**user_payload(row.user), "role": row.role} for row in rows]


@app.post("/api/expenses")
def create_expense(data: ExpenseCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_member(data.group_id, user, db)
    member_ids = list(db.scalars(select(GroupMember.user_id).where(GroupMember.group_id == data.group_id)).all())
    if data.split_type != "equal": raise HTTPException(400, "Only equal splits are currently supported")
    share = (data.amount / len(member_ids)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    expense = Expense(**data.model_dump(), paid_by_id=user.id)
    db.add(expense); db.flush()
    for index, member_id in enumerate(member_ids):
        amount = data.amount - share * (len(member_ids) - 1) if index == len(member_ids) - 1 else share
        db.add(ExpenseShare(expense_id=expense.id, user_id=member_id, amount=amount))
    db.commit(); db.refresh(expense)
    return expense_detail(expense)


def expense_detail(expense: Expense):
    return {"id": expense.id, "title": expense.title, "amount": float(expense.amount), "category": expense.category, "split_type": expense.split_type, "notes": expense.notes, "created_at": expense.created_at.isoformat(), "paid_by": user_payload(expense.paid_by), "shares": [{"user_id": s.user_id, "amount": float(s.amount)} for s in expense.shares]}


@app.get("/api/expenses")
def expenses(group_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Expense).options(joinedload(Expense.paid_by), joinedload(Expense.shares)).join(GroupMember, GroupMember.group_id == Expense.group_id).where(GroupMember.user_id == user.id).order_by(Expense.created_at.desc())
    if group_id: query = query.where(Expense.group_id == group_id)
    return [expense_detail(item) for item in db.scalars(query).unique().all()]


@app.get("/api/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    member_rows = db.scalars(select(GroupMember).where(GroupMember.user_id == user.id)).all()
    group_ids = [row.group_id for row in member_rows]
    if not group_ids: return {"total_spent": 0, "you_are_owed": 0, "you_owe": 0, "net": 0, "recent": [], "by_category": {}}
    items = db.scalars(select(Expense).options(joinedload(Expense.paid_by), joinedload(Expense.shares)).where(Expense.group_id.in_(group_ids)).order_by(Expense.created_at.desc())).unique().all()
    paid = sum((item.amount for item in items if item.paid_by_id == user.id), Decimal(0))
    owed = sum((share.amount for item in items for share in item.shares if share.user_id == user.id), Decimal(0))
    categories = defaultdict(Decimal)
    for item in items: categories[item.category] += item.amount
    return {"total_spent": float(sum((item.amount for item in items), Decimal(0))), "you_are_owed": float(paid - owed) if paid > owed else 0, "you_owe": float(owed - paid) if owed > paid else 0, "net": float(paid - owed), "by_category": {key: float(value) for key, value in categories.items()}, "recent": [expense_detail(item) for item in items[:8]]}


@app.post("/api/settlements")
def settle(data: SettlementCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_member(data.group_id, user, db); require_member(data.group_id, db.get(User, data.to_user_id), db)
    settlement = Settlement(group_id=data.group_id, from_user_id=user.id, **data.model_dump(exclude={"group_id"})); db.add(settlement); db.commit()
    return {"message": "Settlement recorded", "id": settlement.id}


static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(static_dir / "index.html")
