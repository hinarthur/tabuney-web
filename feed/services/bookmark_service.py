# feed/services/bookmark_service.py
from feed.models import SavedWork, Work, WorkLabel
from django.core.exceptions import ValidationError

def save_work(
    *,
    member,
    work_id: int,
    label_id: int | None = None
):
    try:
        work = Work.objects.get(id=work_id)
    except Work.DoesNotExist:
        raise ValidationError("Work does not exist")

    label = None
    if label_id is not None:
        if label_id == 0:
            label, _ = WorkLabel.objects.get_or_create(
                member=member,
                name="bookmark"
            )
        else:
            try:
                label = WorkLabel.objects.get(id=label_id, member=member)
            except WorkLabel.DoesNotExist:
                raise ValidationError("Label not found")

    if SavedWork.objects.filter(
        member=member,
        work=work,
        label=label
    ).exists():
        return None  # already saved

    return SavedWork.objects.create(
        member=member,
        work=work,
        label=label
    )