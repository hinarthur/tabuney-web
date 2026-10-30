import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from game.models import Edition
from member.models import EditionUnlock
from .models import Interaction
from .models import RATING_SCORES

# 排序用的保底時間：兩個時間欄位都是 None 時（理論上不會發生）用它墊底，
# 免得 sorted() 拿 None 跟 datetime 比較而炸掉。tz-aware 才能與 DB 的值相比。
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


@login_required
@require_POST
def update_interaction(request):
    edition_id = request.POST.get("edition_id")
    rating = request.POST.get("rating")
    status = request.POST.get("status")

    edition = get_object_or_404(Edition, id=edition_id)

    # Get or create the interaction for this user and edition
    interaction, created = Interaction.objects.get_or_create(
        member=request.user.member,
        edition=edition
    )

    # Update fields if provided
    if rating is not None:
        # If rating is empty string, set to None
        interaction.rating = rating if rating else None

    if status is not None:
        # If status is empty string, set to None
        interaction.status = status if status else None

    interaction.save()

    return JsonResponse({
        "success": True,
        "rating": interaction.rating,
        "status": interaction.status,
        "message": "Successfully saved"
    })


class CollectionView(LoginRequiredMixin, View):
    """Display user's collection of editions with filtering and sorting options."""

    template_name = "interaction/collection.html"

    def get(self, request):
        # Get filter parameters
        all_statuses = ["past", "owned", "wish"]
        all_ratings = ["amazing", "nice", "nah", "nightmare"]
        status_filter = request.GET.getlist("status", all_statuses)
        rating_filter = request.GET.getlist("rating", all_ratings)
        sort_by = request.GET.get("sort", "-updated_at")

        # Edition Access 不是篩選條件，是**額外的收錄來源**：勾選時，有版本
        # 專享的版本一律列出來，即使它沒有任何收藏狀態或喜好——那種版本在
        # Interaction 表裡可能整筆不存在，光靠 queryset 篩永遠篩不出來。
        #
        # 所以它與 status / rating 的關係是 OR 而不是 AND，預設勾選。表單一律
        # 送出明確的 1/0（不像 status/rating 靠「有沒有這個參數」判斷），否則
        # 取消勾選時什麼都不送，會跟「預設」長得一模一樣、關不掉。
        # 舊版的 access=1 / access=yes 書籤網址都落在「勾選」這邊，不會誤判。
        access_included = request.GET.get("access", "1") != "0"

        member = request.user.member
        # 一次查出 id 與取得時間：取得時間要拿來給「只有版本專享、沒有收藏
        # 狀態」的那些版本當排序依據（它們沒有 Interaction.updated_at 可用）。
        unlock_dates = dict(
            EditionUnlock.objects.filter(member=member)
            .values_list("edition_id", "created_at")
        )
        unlocked_edition_ids = set(unlock_dates)

        # Build queryset
        interactions = Interaction.objects.filter(member=member)

        # Only show interactions the member has actually expressed something about
        # (a collection status, a preference rating, or both).
        interactions = interactions.exclude(
            status__isnull=True, rating__isnull=True
        )

        # Apply status filter: hide items whose status is explicitly deselected.
        # Items with no status (rating only) are always shown.
        if status_filter and set(status_filter) != set(all_statuses):
            interactions = interactions.filter(
                models.Q(status__in=status_filter) | models.Q(status__isnull=True)
            )

        # Apply rating filter: hide items whose rating is explicitly deselected.
        # Items with no rating (null) are always shown.
        if rating_filter and set(rating_filter) != set(all_ratings):
            interactions = interactions.filter(
                models.Q(rating__in=rating_filter) | models.Q(rating__isnull=True)
            )

        # Prefetch related edition data
        interactions = interactions.select_related("edition", "edition__game")

        rows = list(interactions)

        # 把「有版本專享但不在上面清單裡」的版本補進來。兩種情形都算：
        # Interaction 整筆不存在，或存在但 status / rating 全空（上面那條
        # exclude 會把它濾掉）。這兩種都是使用者明明取得了版本專享、卻在收藏
        # 頁找不到的情況。
        if access_included and unlocked_edition_ids:
            missing_ids = unlocked_edition_ids - {row.edition_id for row in rows}
            if missing_ids:
                existing = {
                    row.edition_id: row
                    for row in Interaction.objects.filter(
                        member=member, edition_id__in=missing_ids,
                    ).select_related("edition", "edition__game")
                }
                for edition in Edition.objects.filter(
                    id__in=missing_ids,
                ).select_related("game"):
                    # 沒有 Interaction 的就給一個未存檔的空殼：模板只讀
                    # edition / status / rating，這樣兩種來源的形狀一致，
                    # 也不會為了顯示而在 DB 裡憑空生出收藏紀錄。
                    rows.append(
                        existing.get(edition.id)
                        or Interaction(member=member, edition=edition)
                    )

        rows = self._sort_rows(rows, sort_by, unlock_dates)

        # Get available status choices
        from .models import COLLECTION_STATUS_CHOICES, RATING_CHOICES
        status_choices = COLLECTION_STATUS_CHOICES
        rating_choices = RATING_CHOICES

        # Get sort options with labels
        sort_options = [
            ("-updated_at", "Most Recent"),
            ("rating_score", "Rating (High to Low)"),
            ("edition__name", "Name (A-Z)"),
        ]

        context = {
            "interactions": rows,
            "status_filter": status_filter,
            "rating_filter": rating_filter,
            "sort_by": sort_by,
            "status_choices": status_choices,
            "rating_choices": rating_choices,
            "sort_options": sort_options,
            "RATING_SCORES": RATING_SCORES,
            # 卡片上的 Edition Access 絲帶：模板用 {% if edition.id in ... %} 判斷。
            # 一位會員的解鎖數是個位數，整包丟給模板比逐張卡片查便宜得多。
            "unlocked_edition_ids": unlocked_edition_ids,
            "access_included": access_included,
        }

        return render(request, self.template_name, context)

    @staticmethod
    def _sort_rows(rows, sort_by, unlock_dates):
        """排序合併後的清單。

        以前是交給資料庫 order_by，但清單現在有兩種來源——Interaction 資料列，
        以及「只有版本專享、沒有收藏紀錄」的未存檔空殼——後者根本不在資料庫的
        結果集裡，只能在 Python 這邊一起排。這一頁本來就沒有分頁、全部列都會
        渲染出來，所以不會因此多載入任何東西。

        空殼沒有 updated_at，改用取得版本專享的時間當作「進到收藏的時間」。
        """
        def recency(row):
            return row.updated_at or unlock_dates.get(row.edition_id) or EPOCH

        if sort_by == "edition__name":
            return sorted(rows, key=lambda row: (row.edition.name or "").casefold())
        if sort_by == "rating_score":
            return sorted(
                rows,
                key=lambda row: (RATING_SCORES.get(row.rating, 0), recency(row)),
                reverse=True,
            )
        # 預設與其他所有值：最近更新的在前（對應原本的 "-updated_at"）
        return sorted(rows, key=recency, reverse=True)
