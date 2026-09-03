from fastapi import APIRouter

# Placeholder for future project media endpoints (e.g. uploading/listing/deleting
# files attached to a project). No feature has specified this behavior yet — this
# router is intentionally empty until such a feature is specified and planned.
router = APIRouter(prefix="/projects", tags=["projects", "media"])
