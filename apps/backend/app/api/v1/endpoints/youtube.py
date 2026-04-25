import jwt
from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.v1.deps import CurrentUser, DB
from app.core.config import settings
from app.schemas.youtube import (
    YouTubeCallbackResponse,
    YouTubeConnectResponse,
    YouTubeMetadataUpdateRequest,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    YouTubeVideoStatsResponse,
)
from app.services.youtube import YouTubeService

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/connect", response_model=YouTubeConnectResponse)
async def connect_youtube(
    channel_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> YouTubeConnectResponse:
    svc = YouTubeService(db)
    await svc.get_owned_channel(
        channel_id=channel_id,
        owner_id=str(current_user.id),
        org_id=str(current_user.organization_id),
    )

    redirect_uri = settings.youtube_redirect_uri or str(request.url_for("youtube_callback"))
    state = svc.build_state_token(
        channel_id=channel_id,
        user_id=str(current_user.id),
        org_id=str(current_user.organization_id),
    )
    auth_url = svc.build_connect_url(state=state, redirect_uri=redirect_uri)
    return YouTubeConnectResponse(auth_url=auth_url, state=state)


@router.get("/callback", response_model=YouTubeCallbackResponse, name="youtube_callback")
async def youtube_callback(
    request: Request,
    db: DB,
    code: str = Query(...),
    state: str = Query(...),
) -> YouTubeCallbackResponse:
    try:
        state_data = jwt.decode(
            state,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience="youtube-oauth-state",
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "aud", "iss", "type"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    if state_data.get("type") != "youtube_oauth_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state type")

    svc = YouTubeService(db)
    channel = await svc.get_owned_channel(
        channel_id=state_data["channel_id"],
        owner_id=state_data["sub"],
        org_id=state_data["org"],
    )

    redirect_uri = settings.youtube_redirect_uri or str(request.url_for("youtube_callback"))
    channel = await svc.connect_channel_with_code(
        channel=channel,
        code=code,
        redirect_uri=redirect_uri,
    )

    return YouTubeCallbackResponse(
        channel_id=channel.id,
        youtube_channel_id=channel.youtube_channel_id or "",
        connected=True,
    )


@router.post("/upload", response_model=YouTubeUploadResponse)
async def upload_video(
    payload: YouTubeUploadRequest,
    current_user: CurrentUser,
    db: DB,
) -> YouTubeUploadResponse:
    svc = YouTubeService(db)
    channel = await svc.get_owned_channel(
        channel_id=str(payload.channel_id),
        owner_id=str(current_user.id),
        org_id=str(current_user.organization_id),
    )
    result = await svc.upload_video(channel=channel, payload=payload.model_dump(mode="json"))
    return YouTubeUploadResponse(**result)


@router.patch("/videos/{youtube_video_id}/metadata", status_code=status.HTTP_204_NO_CONTENT)
async def update_video_metadata(
    youtube_video_id: str,
    payload: YouTubeMetadataUpdateRequest,
    current_user: CurrentUser,
    db: DB,
) -> None:
    svc = YouTubeService(db)
    channel = await svc.get_owned_channel(
        channel_id=str(payload.channel_id),
        owner_id=str(current_user.id),
        org_id=str(current_user.organization_id),
    )
    await svc.update_metadata(
        channel=channel,
        youtube_video_id=youtube_video_id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        visibility=payload.visibility,
    )


@router.get("/videos/{youtube_video_id}/stats", response_model=YouTubeVideoStatsResponse)
async def get_video_stats(
    youtube_video_id: str,
    channel_id: str,
    current_user: CurrentUser,
    db: DB,
) -> YouTubeVideoStatsResponse:
    svc = YouTubeService(db)
    channel = await svc.get_owned_channel(
        channel_id=channel_id,
        owner_id=str(current_user.id),
        org_id=str(current_user.organization_id),
    )
    stats = await svc.get_video_stats(channel=channel, youtube_video_id=youtube_video_id)
    return YouTubeVideoStatsResponse(**stats)
