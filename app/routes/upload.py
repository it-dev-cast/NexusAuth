from fastapi import APIRouter, Depends, File, UploadFile

from app.core.config import get_settings
from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.core.uploads import save_employee_photo
from app.models.user import User


router = APIRouter(
    prefix="/api/v1/uploads",
    tags=["Uploads"],
)

# Same permission as writing an Employee record — uploading a photo is part
# of that same action, not a separate resource of its own.
require_writer = require_roles(*allowed_roles("employee", "write"))


@router.post("/employee-photo", status_code=201)
async def upload_employee_photo_endpoint(
    file: UploadFile = File(...),
    current_user: User = Depends(require_writer),
):
    settings = get_settings()
    url = await save_employee_photo(file, settings.upload_dir, settings.upload_max_bytes)
    return api_ok({"url": url})
