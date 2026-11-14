from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List,Annotated
from mysite.database.models import Group, GroupPeople
from mysite.database.schema import GroupCreateSchema, GroupUpdateSchema, GroupOutputSchema
from mysite.database.db import SessionLocal
from .dependencies import get_current_user


group_router = APIRouter(prefix='/groups', tags=['Groups'])


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@group_router.post('/create/', response_model=GroupOutputSchema)
async def group_create(group: GroupCreateSchema,current_user: Annotated[dict, Depends(get_current_user)],
                       db: Session = Depends(get_db)):
    group_db = Group(group_name=group.group_name, owner=current_user['id'])
    db.add(group_db)
    db.flush()

    group_people_db = GroupPeople(group_id=group_db.id, user=current_user['id'])

    db.add(group_people_db)
    db.commit()
    db.refresh(group_db)

    return group_db

@group_router.get('/', response_model=List[GroupOutputSchema])
async def group_list(current_user: Annotated[dict, Depends(get_current_user)]
                     ,db: Session = Depends(get_db)):
    return (db.query(Group).join(GroupPeople,Group.id == GroupPeople.id).
            filter(GroupPeople.user==current_user['id']).all())


@group_router.get('/{group_id}/', response_model=GroupOutputSchema)
async def group_detail(group_id: int,current_user: Annotated[dict, Depends(get_current_user)],
                       db: Session = Depends(get_db)):
    group_db = db.query(Group).filter(Group.id == group_id).first()

    if not group_db:
        raise HTTPException(detail='Мындай группа жок', status_code=404)

    member = db.query(GroupPeople).filter(GroupPeople.group_id ==
                                 group_id,GroupPeople.user == current_user['id']).first()
    
    if not member:
        raise HTTPException(detail='Сиз бул групада жоксуз', status_code=404)

    return group_db


@group_router.put('/{group_id}/', response_model=dict)
async def group_update(group_id: int,current_user: Annotated[dict, Depends(get_current_user)],
                       group: GroupUpdateSchema, db: Session = Depends(get_db)):
    group_db = db.query(Group).filter(Group.id == group_id).first()

    if not group_db:
        raise HTTPException(detail='Мындай группа жок', status_code=404)

    if group_db.owner != current_user['id']:
        raise HTTPException(detail='Групанын ээси озгортуу кылат', status_code=403)

    group_db.group_name = group.group_name


    db.commit()
    db.refresh(group_db)

    return {'message': 'Группанын маалыматы өзгөртүлдү'}

@group_router.delete('/{group_id}/', response_model=dict)
async def group_delete(group_id: int,current_user: Annotated[dict, Depends(get_current_user)],
                       db: Session = Depends(get_db)):
    group_db = db.query(Group).filter(Group.id == group_id).first()

    if not group_db:
        raise HTTPException(detail='Мындай группа жок', status_code=404)

    if group_db.owner != current_user['id']:
        raise HTTPException(detail='Групанын ээси жок кылат', status_code=403)

    db.delete(group_db)
    db.commit()

    return {'message': 'Группа өчүрүлдү'}
