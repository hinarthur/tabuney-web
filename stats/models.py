from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from member.models import Member


class SearchLog(models.Model):
    SEARCH_TYPE_CHOICES = (
        ('edition', 'Edition'),
    )

    # 使用者實際打了什麼形狀的東西（由字串推斷，不代表有沒有搜到）
    INPUT_KIND_CHOICES = (
        ('barcode', '條碼'),
        ('text', '文字'),
    )

    # search_editions() 停在哪一階：條碼 → Edition 名稱 → Game 標題
    MATCHED_BY_CHOICES = (
        ('barcode', '條碼'),
        ('edition_name', 'Edition 名稱'),
        ('game_title', 'Game 標題'),
        ('none', '未命中'),
    )

    SOURCE_CHOICES = (
        ('web', '網站'),
        ('app', 'App'),
    )

    keyword = models.CharField(max_length=255)
    search_type = models.CharField(max_length=20, choices=SEARCH_TYPE_CHOICES)
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    # null = 未知（本欄位上線前的舊資料），與 0（真的沒搜到）語意不同，不要改成 default=0
    result_count = models.PositiveIntegerField(null=True, blank=True)
    matched_by = models.CharField(
        max_length=20, choices=MATCHED_BY_CHOICES, blank=True, default=''
    )
    # 掃了條碼卻沒命中時 input_kind='barcode' 而 matched_by='none'，
    # 這組合就是「該補哪款遊戲」最強的訊號，所以兩個都要存。
    input_kind = models.CharField(
        max_length=20, choices=INPUT_KIND_CHOICES, blank=True, default=''
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, blank=True, default=''
    )
    lang = models.CharField(max_length=10, blank=True, default='')
    # 沒有 session_key：已登入者用 member 串連（跨 session/裝置都不會斷），
    # 匿名者不記任何識別碼，站上因此不需要對訪客寫任何 cookie。
    is_bot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['search_type', 'created_at']),
            models.Index(fields=['keyword']),
            # 報表主查詢：排除爬蟲、找未命中、限時間範圍
            models.Index(fields=['is_bot', 'result_count', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.search_type}] {self.keyword}"


class ViewLog(models.Model):
    # 用 ContentType 讓它通用於任何 model（Product, News, ...）
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)  # Changed from PositiveIntegerField to support UUIDs
    content_object = GenericForeignKey('content_type', 'object_id')

    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['content_type', 'object_id', 'created_at']),
        ]

    def __str__(self):
        return f"View: {self.content_type.model} #{self.object_id}"


class PageVisit(models.Model):
    """
    指定頁面的到訪次數，一天一列累加。頁面清單見 PAGE_CHOICES，新增頁面追蹤
    時要在那裡加一項——log_page_visit() 只接受清單內的值，寫錯字會直接炸掉，
    不會默默生出一個追蹤不到的頁面。

    比照站方隱私原則對 Edition.view_count 的取捨：不記任何識別碼，匿名訪客
    不去重，語意是「頁面載入次數」而非「不重複訪客數」。
    """
    PAGE_CHOICES = (
        ('home', '首頁'),
        ('membership', '會員方案'),
        ('game_search', '遊戲搜尋'),
        ('about', '關於我們'),
        ('feed_list', '情報牆'),
    )

    page = models.CharField(max_length=30, choices=PAGE_CHOICES)
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date']
        unique_together = ('page', 'date')

    def __str__(self):
        return f"[{self.page}] {self.date}: {self.count}"


class LanguageClick(models.Model):
    """
    語言切換的點擊次數，一天一列累加。兩種事件：
      menu_open —— 點開頂 bar 那顆地球按鈕（桌機與手機合併計），lang 一律空字串
      select    —— 在選單裡點了某個介面語言，lang 是該語言碼

    兩者語意刻意不重疊：menu_open 是「有多少人想找語言切換」，select 是「最後選了
    什麼」，相減就看得出有多少人打開了卻沒切。

    比照 PageVisit 的隱私取捨：不記 member、不記 session_key、不記 IP，語意是
    「點擊次數」而非不重複人數。

    也刻意不做 log_page_visit() 那種 30 分鐘去重——同一個人短時間內連切幾種語言
    正好是「他在找看得懂的版本」的訊號，去重會把這件事抹掉。
    """
    KIND_CHOICES = (
        ('menu_open', '點開語言選單'),
        ('select', '選擇語言'),
    )

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # 只存 settings.LANGUAGES 那六碼（介面語言）；kind='menu_open' 時為空字串
    lang = models.CharField(max_length=10, blank=True, default='')
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date']
        unique_together = ('kind', 'lang', 'date')

    def __str__(self):
        return f"[{self.kind}{'/' + self.lang if self.lang else ''}] {self.date}: {self.count}"


class PageVisitCooldown(models.Model):
    """
    已登入會員在指定頁面最近一次被計入到訪的時間，用來做 30 分鐘去重。

    匿名訪客沒有識別碼可去重，所以這張表只存會員；語意跟 log_view() 對
    ViewLog 的 member 去重一致，只是這裡不需要保留逐筆紀錄，只要「最後一次」。
    """
    page = models.CharField(max_length=30, choices=PageVisit.PAGE_CHOICES)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    last_seen_at = models.DateTimeField()

    class Meta:
        unique_together = ('page', 'member')

    def __str__(self):
        return f"[{self.page}] {self.member}: {self.last_seen_at}"


class ErrorLog(models.Model):
    """
    使用者撞到的 HTTP 錯誤，一天一列累加。

    重點是 referer：它才回答得了「是哪個頁面、哪條連結把人送到這裡的」。path
    只告訴你哪個網址壞了，referer 告訴你哪一頁正在放那條壞連結——站內連結失效
    幾乎都是靠這一欄找到源頭。

    刻意做成聚合而非逐筆：404 會被掃描器打到爛，逐筆存幾天就是幾十萬列。這裡
    的資料量上限是「每天 × 每組(狀態碼, path, referer, 例外)」，可控。代價是
    看不到單次事件的時間點，只有 last_seen_at；要細到逐筆時該用 APM 而不是這張表。

    unique_together 用 fingerprint 而不是直接用 path + referer：PostgreSQL 的
    B-tree 索引列有大小上限，兩個 500 字元的欄位湊在一起遇到超長惡意網址會直接
    寫入失敗。fingerprint 是定長雜湊，長度可控。

    比照站方隱私原則（見 PageVisit）：不記 IP、不記 session_key、不留 User-Agent
    原文，只留一個 is_bot 布林值。path 與 referer 都已去掉 query string，避免把
    網址列上的個資（token、email、重設密碼碼）順手存進資料庫。
    """

    # sha1(status_code|path|referer|exception|is_bot)，見 stats.utils._error_fingerprint
    fingerprint = models.CharField(max_length=40)
    status_code = models.PositiveSmallIntegerField()
    path = models.CharField(max_length=500)
    # 空字串＝使用者直接輸入網址或來源被瀏覽器擋掉，不代表沒有來源
    referer = models.CharField(max_length=500, blank=True, default='')
    # 只有 5xx 會有值：例外類別名稱 + 訊息開頭，用來分辨同一個 path 的不同壞法
    exception = models.CharField(max_length=200, blank=True, default='')
    is_bot = models.BooleanField(default=False)

    date = models.DateField()
    count = models.PositiveIntegerField(default=0)
    # 已登入會員撞到的次數。刻意不存 member 本身：那會讓聚合維度爆炸，而這裡
    # 要回答的是「這個錯誤有沒有打到真實用戶」，不是「打到誰」。
    member_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ['-date', '-count']
        unique_together = ('fingerprint', 'date')
        indexes = [
            # 報表主查詢：排除爬蟲、限時間範圍、依狀態碼分流
            models.Index(fields=['is_bot', 'date', 'status_code']),
            models.Index(fields=['status_code', 'date']),
        ]

    def __str__(self):
        return f"[{self.status_code}] {self.path} @ {self.date}: {self.count}"


class ErrorAlertAck(models.Model):
    """
    admin 首頁錯誤警示的「已處理」標記。

    警示不是資料表裡的一列，是 stats.reports.error_insights() 每次即時從 ErrorLog
    算出來的，所以沒辦法在 ErrorLog 上加旗標。這裡記的是「某一條警示在某個時間點
    被看過了」：只要那條警示的 last_at 沒有晚於 acked_at，就不再出現；修好之後
    同一個網址又出錯，last_at 會往後跳，警示自動回來。

    key 是 sha1(kind|path|referer)，理由同 ErrorLog.fingerprint：兩個 500 字元
    的欄位直接做 unique 會撞到 PostgreSQL 索引列的大小上限。
    """

    key = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=20)
    # 只是給 admin 列表看的，比對一律走 key
    path = models.CharField(max_length=500)
    referer = models.CharField(max_length=500, blank=True, default='')
    acked_at = models.DateTimeField()
    acked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['-acked_at']

    def __str__(self):
        return f"[{self.kind}] {self.path} @ {self.acked_at}"


class ServerSample(models.Model):
    """
    VPS 負荷採樣，由 django-q 排程 stats.tasks.sample_server 每 10 分鐘寫一列。

    容器裡讀 /proc/meminfo、/proc/loadavg 拿到的是 host 的數字（沒有掛 lxcfs），
    所以這裡看到的就是整台 VPS，不是單一容器。只留 14 天，約 2000 列。
    deploy/vps/ 的 mem-snapshot 仍然是出事當下的細節來源，這張表只負責走勢。
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    mem_total_mb = models.PositiveIntegerField()
    mem_available_mb = models.PositiveIntegerField()
    swap_used_mb = models.PositiveIntegerField()
    load1 = models.FloatField()
    load5 = models.FloatField()
    disk_used_pct = models.FloatField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at}: avail {self.mem_available_mb}MB, swap {self.swap_used_mb}MB"
