from django.contrib.auth.models import User
from django.test import TestCase

from translation.models import Tribe

from .models import Member, Tier

# 注意：member app 的 migration 只 seed 了 code='free' 這一筆 Tier
# （'basic' 已在 0018_retire_basic_tier 退場）；'member'/'subscriber'/'admin'
# 是後來在正式環境的 admin 手動建立的，測試 DB 不會有，所以測試裡一律自己
# create，用不會撞到 'free' 的 test_* code。


class MemberCanLimitTests(TestCase):
    def setUp(self):
        # Member.tribe 預設 default=1（pk=1 的 Tribe），使用者建立時的 signal
        # 會建立 Member(tribe_id=1)，先確保該 Tribe 存在，否則 FK 會炸。
        Tribe.objects.get_or_create(pk=1, defaults={"language": "en", "name": "English"})
        self.tier = Tier.objects.create(
            code='test_member', name='Test Member',
            limits={'script': 1, 'flowchart_print': 0, 'prompt_per_week': 13},
        )
        self.user = User.objects.create(username='u1')
        self.member = Member.objects.get(id=self.user.id)
        self.member.tier_new = self.tier
        self.member.save()

    def test_can_true_for_nonzero_flag(self):
        self.assertTrue(self.member.can('script'))

    def test_can_false_for_zero_flag(self):
        self.assertFalse(self.member.can('flowchart_print'))

    def test_can_default_when_key_missing(self):
        # flowchart_translate 不在這個 tier 的 limits 裡 -> 回退 registry default (0)
        self.assertFalse(self.member.can('flowchart_translate'))

    def test_limit_returns_int(self):
        self.assertEqual(self.member.limit('prompt_per_week'), 13)

    def test_limit_default_unlimited_when_missing(self):
        tier2 = Tier.objects.create(code='test_free', name='Test Free', limits={})
        self.member.tier_new = tier2
        self.member.save()
        # prompt_per_week 完全不在 limits 裡 -> registry default -1（既有的 fail-open 行為，明確記錄）
        self.assertEqual(self.member.limit('prompt_per_week'), -1)

    def test_legacy_string_encoded_json(self):
        self.tier.limits = '{"script": 1}'
        self.tier.save()
        self.member.refresh_from_db()
        self.assertTrue(self.member.can('script'))

    def test_malformed_non_int_value_does_not_raise(self):
        self.tier.limits = {'prompt_per_week': 'not-a-number'}
        self.tier.save()
        self.member.refresh_from_db()
        self.assertEqual(self.member.limit('prompt_per_week'), 0)

    def test_unregistered_key_fails_closed(self):
        self.assertFalse(self.member.can('totally_made_up_key'))
        self.assertEqual(self.member.limit('totally_made_up_key'), 0)

    def test_no_tier_assigned(self):
        self.member.tier_new = None
        self.member.save()
        self.assertFalse(self.member.can('script'))
        self.assertEqual(self.member.limit('prompt_per_week'), -1)  # registry default applies even w/o tier

    def test_tier_code_normalizes_basic_to_member(self):
        # 'basic' tier 本身已退場（member/migrations/0018_retire_basic_tier.py），
        # 但 tier_code 保留了防禦性的正規化——萬一未來又手動建立一筆 code='basic'
        # 的 Tier，顯示上仍要併入 'member'，不會露出內部代碼。
        basic = Tier.objects.create(code='basic', name='Basic', limits={})
        self.member.tier_new = basic
        self.member.save()
        self.assertEqual(self.member.tier_code, 'member')

    def test_tier_code_passthrough_for_subscriber_and_admin(self):
        sub = Tier.objects.create(code='subscriber', name='Subscriber', limits={})
        self.member.tier_new = sub
        self.member.save()
        self.assertEqual(self.member.tier_code, 'subscriber')

        admin_tier = Tier.objects.create(code='admin', name='Admin', limits={})
        self.member.tier_new = admin_tier
        self.member.save()
        self.assertEqual(self.member.tier_code, 'admin')

    def test_is_subscriber_or_higher_includes_admin(self):
        admin_tier = Tier.objects.create(code='admin', name='Admin', limits={})
        self.member.tier_new = admin_tier
        self.member.save()
        self.assertTrue(self.member.is_subscriber_or_higher)

    def test_is_subscriber_or_higher_false_for_member_tier(self):
        self.assertFalse(self.member.is_subscriber_or_higher)

    def test_tier_code_free_without_tier_new(self):
        # tier_legacy 欄位已移除，沒有 tier_new 時一律視為 free，沒有其他 fallback。
        self.member.tier_new = None
        self.member.save()
        self.assertEqual(self.member.tier_code, 'free')
