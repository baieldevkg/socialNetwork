from fastapi import APIRouter,HTTPException,WebSocket,WebSocketDisconnect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.util import await_
from starlette import status
from mysite.database.db import SessionLocal
from mysite.clients.auth_service import verify_access_token
from mysite.database.models import Group,GroupPeople,GroupMessage


websocket_router = APIRouter(prefix='/ws',tags=['Websocket'])

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, group_id: int, websocket: WebSocket):
        await websocket.accept()

        if group_id not in self.active_connections:
            self.active_connections[group_id] = []

        self.active_connections[group_id].append(websocket)

    async def disconnect(self, group_id: int, websocket: WebSocket):
        connections = self.active_connections.get(group_id)

        # if not connections:
        #     return HTTPException(detail='Байланыш жок', status_code=400)

        if websocket in connections:
            connections.remove(websocket)

        if not connections:
            self.active_connections.pop(group_id, None)

    async def broadcast(self, group_id: int, data: dict):
        connections = self.active_connections.get(group_id, [])

        disconnected_connections = []

        for i in connections.copy():
            try:
                await i.send_json(data)
            except RuntimeError:
                disconnected_connections.append(i)

        for i in disconnected_connections:
            await self.disconnect(group_id,i)

manager = ConnectionManager()

@websocket_router.websocket('/groups/{group_id}/')
async def group_chat_websocket(websocket: WebSocket, group_id: int, access_token: str):
    global current_user

    try:
        current_user = await verify_access_token(access_token)
    except HTTPException as error:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(error.detail))
        return
    db = SessionLocal()

    try:
        group_db = db.query(Group).filter(Group.id==group_id).first()

        if not group_db:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Мындай група жок")
            return

        member_db = (db.query(GroupPeople).filter(GroupPeople.group_id==group_id,
                                               GroupPeople.user==current_user['id']).first())

        if not member_db:
            await websocket.close(code = status.WS_1008_POLICY_VIOLATION,reason='Сиз бул группада жоксуз')
            return

    finally:
        db.close()

    await manager.connect(group_id, websocket)

    await websocket.send_json(
        {
            "type": "connecton.established",
            "data": {
                "group_id": group_id,
                "user": current_user['id'],
                "username": current_user['username']
            },
        }
    )

    try:
        while True:
            message_text = await websocket.receive_text()
            message_text = message_text.strip()

            if not message_text:
                await websocket.send_json(
                    {
                        'type': 'error',
                        "detail": "Билдируу бош болбошу керек"
                    }
                )
                continue

            if len(message_text) > 5000:
                await websocket.send_json(
                    {
                        'type': 'error',
                        "detail": "Билдируу 5000 белгиден ашпашы керек"
                    }
                )
                continue

            db = SessionLocal()

            try:
                message_db = GroupMessage(
                    group_id = group_id,
                    user=current_user['id'],
                    message=message_text
                )

                db.add(message_db)
                db.commit()
                db.refresh(message_db)

                message_data = {
                    "type": "message.created",
                    "data": {
                        "id": message_db.id,
                        "group_id": message_db.group_id,
                        "user": message_db.user,
                        "username": current_user['username'],
                        "message": message_db.message,
                        "created_date": str(message_db.created_date)
                    }
                }

            except SQLAlchemyError:
                db.rollback()

                await websocket.send_json(
                    {
                        "type": 'error',
                        "detail": 'Билдируу сакталган жок'
                    }
                )
                continue

            finally:
                db.close()

            await manager.broadcast(group_id,message_data)
    except WebSocketDisconnect:
        await manager.disconnect(group_id, websocket)