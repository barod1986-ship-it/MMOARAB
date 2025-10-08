# MMOARAB CORE - Design Documentation
## توثيق تصميم الإضافة

**آخر تحديث:** 2025-10-03

---

## 🎨 **التحديثات الجديدة**

### ✨ **إضافات v1.0.0:**

1. **Quick Info Bar** - شريط معلومات سريع
   - العنوان + التقييم + الموقع الرسمي في خط واحد
   - متصل بالصورة المميزة (border-radius)
   - Gradient background داكن
   - Responsive (ينزل سطرين بالموبايل)
   - **نجمة SVG ديناميكية** تمتلئ حسب التقييم (45x45px)
   - أرقام ذهبية `#FFD700` بنفس لون النجمة
   - موقع رسمي بلون أحمر `#b30000` مع hover effect

2. **Media Containers** - حاويات منفصلة
   - كل من Review/Trailer/Gallery في container منفصل
   - خلفية `#1E1E1E` مع border و shadow
   - Padding `40px` و border-radius `12px`

3. **Overall Rating Redesign** - تصميم جديد
   - عرض أفقي (خط واحد) بدل عمودي
   - ألوان محدثة: أزرق داكن بدل بنفسجي
   - Flexbox مع `justify-content: center`

4. **إزالة التكرار**
   - حذف الموقع الرسمي من قسم معلومات اللعبة
   - موجود فقط في Quick Info Bar

5. **Related News Section** - قسم الأخبار المرتبطة
   - عرض 3 كروت أخبار في صف واحد
   - Grid layout: `repeat(3, 1fr)`
   - Placeholder للصور المفقودة (📰)
   - داخل `mcp-media-container` للتناسق

---

## 📄 صفحة اللعبة الفردية (Single Game Page)

### الملفات:
- **Template:** `templates/single-game.php`
- **CSS:** `assets/css/single-game.css`

### الأقسام الرئيسية:

#### 1. Hero Section (البطل)
```
├── Featured Image (الصورة المميزة)
└── Quick Info Bar
    ├── Game Title (عنوان اللعبة)
    ├── Rating Badge (⭐ 8.5/10)
    └── Official Website Button (🌐)
```

**التصميم:**
- صورة مميزة responsive مع `border-radius: 12px 12px 0 0`
- Quick Info Bar متصل بالصورة
- Gradient background: `#1a1a1a → #2d2d2d`
- **نجمة SVG ديناميكية:**
  - حجم: 45x45 بكسل
  - تمتلئ بالذهبي حسب نسبة التقييم (linearGradient)
  - animation: starPulse (توهج وتكبير)
  - لون الامتلاء: `#FFD700` (ذهبي) → `#555` (رمادي)
  - inline styles للألوان لتجنب مشاكل cache
- **أرقام التقييم:**
  - الرقم الأول: `#FFD700` (ذهبي - bold)
  - `/10`: `#FFD700` مع opacity 0.8
- **زر الموقع الرسمي:**
  - خلفية: `#b30000` (أحمر)
  - hover: `#990000` (أحمر غامق)
  - shadow: أحمر شفاف

---

#### 2. Game Information (معلومات اللعبة)
```
├── Developer (المطور) 👨‍💻
├── Publisher (الناشر) 🏢
├── Release Date (تاريخ الإصدار) 📅
├── Official Website (الموقع الرسمي) 🌐
├── Game Type (نوع اللعبة) 🎮
├── Game Status (حالة اللعبة) ✅
├── Game Mode (طريقة اللعب) 🕹️
├── Game Platform (المنصات) 💻
└── Game Engine (محرك اللعبة) ⚙️
```

**الأيقونات:**
- 👨‍💻 **Developer:** أيقونة المطور
- 🏢 **Publisher:** أيقونة الشركة الناشرة
- 📅 **Release Date:** أيقونة التاريخ
- 🌐 **Official Website:** أيقونة الموقع الإلكتروني
- 🎮 **Game Type:** أيقونة نوع اللعبة
- ✅ **Game Status:** أيقونة حالة اللعبة
- 🕹️ **Game Mode:** أيقونة طريقة اللعب
- 💻 **Game Platform:** أيقونة المنصات
- ⚙️ **Game Engine:** أيقونة محرك اللعبة

**التصميم:**
- Grid Layout: `repeat(auto-fit, minmax(250px, 1fr))`
- Cards بخلفية داكنة `#1E1E1E`
- أيقونة Emoji بجانب كل عنوان
- Hover effects
- Font-size للأيقونات: 1.5em
- Border-radius: 12px

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333` (رمادي داكن)
- Border Left: `var(--theme-link-color)` (ملون)
- Text: `#e0e0e0` (فاتح)
- Hover Shadow: `rgba(0,0,0,0.4)`

---

#### 3. Content Section (المحتوى)
```
└── Game Description (وصف اللعبة)
```

**التصميم:**
- Line-height: 1.8
- Font-size: 1.1em
- محتوى كامل من WordPress Editor

---

#### 4. Features Section (قسم المميزات)
```
└── 4 Feature Cards في صف واحد
```

**التصميم:**
- Grid: `repeat(4, 1fr)`
- Cards داكنة `#1E1E1E` مع border
- أيقونة ✓ دائرية بـ gradient على اليسار
- Hover: ترتفع قليلاً مع shadow

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333`
- Text: `#e0e0e0` (فاتح)
- Checkmark: `linear-gradient(135deg, #0073aa 0%, #667eea 100%)`
- Hover Shadow: `rgba(0,0,0,0.4)`

**Responsive:**
- Desktop (>1024px): 4 أعمدة
- Tablet (≤1024px): عمودين
- Mobile (≤768px): عمود واحد

---

#### 5. Gallery Section (معرض الصور)
```
└── Grid من الصور + Lightbox (نافذة منبثقة)
```

**التصميم:**
- Grid: `repeat(4, 1fr)` - 4 صور في صف واحد
- Images: 200px height
- Gap: 20px
- Border-radius: 12px
- Hover: تكبير الصورة قليلاً (scale 1.1) + ظل

**الوظيفة - Lightbox:**
- 📌 **عند النقر على صورة:** تفتح في نافذة منبثقة (popup) فوق الصفحة
- **الخلفية:** تصبح سوداء شفافة (rgba(0,0,0,0.9))
- **الصورة:** تظهر بالحجم الكامل في المنتصف
- **زر الإغلاق:** × في الزاوية اليمنى العليا
- **أزرار التنقل:** ← → على جانبي الصورة
- **الإغلاق:** بالضغط على X أو خارج الصورة أو ESC

**التنقل:**
- ⬅️ **السهم الأيسر:** الصورة السابقة (أو ◀ keyboard)
- ➡️ **السهم الأيمن:** الصورة التالية (أو ▶ keyboard)
- التنقل دائري (من آخر صورة → أول صورة)
- أزرار شفافة مع hover effect

**المميزات:**
- الصور المعروضة: Medium size (للسرعة)
- الصور في الـ Lightbox: Full size (جودة عالية)
- لا تفتح في تاب جديد - تبقى في نفس الصفحة
- Smooth fade-in animation
- دعم كامل للوحة المفاتيح (← → ESC)

**Responsive:**
- Desktop (>1024px): 4 أعمدة
- Tablet (≤1024px): عمودين
- Mobile (≤768px): عمود واحد

---

#### 6. Trailer Section (المقطع الدعائي)
```
└── YouTube Embed مع Aspect Ratio 16:9
```

**التصميم:**
- Aspect Ratio Container: 16:9 ثابت
- Position: relative + absolute للـ iframe
- Padding-bottom: 56.25% (للحفاظ على النسبة)
- Border-radius: 12px
- Box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15)
- Background: #000 (للتحميل)

**الوظيفة:**
- تحويل تلقائي لروابط YouTube إلى embed
- دعم: youtube.com/watch, youtube.com/embed, youtu.be
- إذا لم يكن رابط YouTube: زر "شاهد المقطع الدعائي" بتصميم gradient

**زر الرابط البديل:**
- Background: linear-gradient(135deg, #FF0000, #CC0000)
- Padding: 15px 35px
- Border-radius: 30px
- Font-weight: 700
- Box-shadow: 0 4px 20px rgba(255, 0, 0, 0.4)
- Hover: transform + shadow أقوى

---

#### 7. Ratings Section (قسم المراجعات)
```
├── Story Rating (تقييم القصة) 📖
├── Gameplay Rating (تقييم طريقة اللعب) 🎮
├── Graphics Rating (تقييم الرسومات) 🎨
├── Audio Rating (تقييم الصوتيات) 🎵
└── Overall Rating (التقييم العام) ⭐
```

**التصميم - التقييمات الأربعة:**
- Grid: `repeat(4, 1fr)`
- Cards داكنة `#1E1E1E` مع border
- Header بداخله العنوان والتقييم
- Progress bar ملون بـ gradient
- أيقونة emoji شفافة في الخلفية
- Notes (الملاحظات) تحت كل تقييم

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333`
- Text: `#e0e0e0` (فاتح)
- Notes: `#a0a0a0` (رمادي فاتح)
- Progress Bar: `linear-gradient(90deg, #0073aa 0%, #667eea 100%)`
- Hover Border: `var(--theme-link-color)`
- Hover Shadow: `rgba(0,0,0,0.4)`

**التصميم - التقييم العام:**
- خلفية: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` (gradient بنفسجي)
- الرقم: ذهبي `#FFD700` بحجم 2em
- "/10": نفس اللون والحجم مع opacity: 0.7
- نجوم ملونة (كاملة/نصف/فارغة) بحجم 2.5em
- Border: `#333`
- Border-radius: 12px
- Text-shadow للرقم: 0 4px 8px rgba(0, 0, 0, 0.4)

**نظام النجوم:**
- نجمة كاملة: `#FFD700` (ذهبي)
- نجمة نصف: `linear-gradient(90deg, #FFD700 50%, #444 50%)`
- نجمة فارغة: `#444` (رمادي)
- عدد النجوم: 10 (من 10)
- حساب تلقائي للنجوم الكاملة والنصف والفارغة

**الألوان:**
- Background: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` (gradient)
- Border: `#333`
- Overall Value: `#FFD700` (ذهبي)
- Max Score: `#FFD700` مع opacity: 0.7
- Shadow: `0 10px 30px rgba(103, 126, 234, 0.3)` (ظل بنفسجي)

**Responsive:**
- Desktop (>1024px): 4 أعمدة
- Tablet (≤1024px): عمودين
- Mobile (≤768px): عمود واحد

---

#### 8. Related Posts Section (الأخبار ذات الصلة)
```
└── 3 Latest News Posts
```

**التصميم:**
- Grid من 3 بطاقات
- صورة + عنوان + تاريخ + excerpt
- خلفية داكنة `#1E1E1E`
- Border: `#333`

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333`
- Title: يأخذ من `--theme-heading-3-color` (بلوكسي)
- Date: `#a0a0a0`
- Excerpt: `#b0b0b0`
- Hover Shadow: `rgba(0,0,0,0.4)`

---

#### 9. Comments Section (قسم التعليقات)
```
└── WordPress Comments System
```

**التصميم:**
- نظام التعليقات الافتراضي من WordPress
- خلفية داكنة `#1E1E1E`
- تنسيق مخصص يتناسب مع التصميم العام
- دعم الردود المتداخلة (Threaded Comments)

**الألوان:**
- Section Background: `#1E1E1E` (داكن)
- Form Background: `#252525` (أغمق قليلاً)
- Border: `#333`
- Input Background: `#1a1a1a`
- Input Border: `#333`
- Input Text: `#fff`
- Submit Button: `var(--theme-link-color, #0073aa)`
- Submit Button Hover: `var(--theme-link-hover-color, #005a87)`
- Comment Background: `#252525`
- Author Name: `#fff`
- Comment Content: `#b0b0b0`

**المميزات:**
- ✅ تكامل كامل مع نظام WordPress
- ✅ دعم التصديق والموافقة
- ✅ حماية من السبام
- ✅ إشعارات بريدية
- ✅ تنسيق مخصص متناسق مع التصميم الداكن
- ✅ يعمل مع جميع إضافات التعليقات

**التفعيل:**
1. التعليقات مفعلة تلقائياً في CPT
2. يمكن تفعيلها/إيقافها لكل لعبة من صندوق "مناقشة"
3. إعدادات عامة من: إعدادات → مناقشة

---

## 📚 صفحة الأرشيف (Archive Games Page)

### الملفات:
- **Template:** `templates/archive-game.php`
- **CSS:** `assets/css/archive-game.css`

### الأقسام الرئيسية:

#### 1. Archive Header (رأس الصفحة)
```
├── Page Title: "أرشيف الألعاب"
└── Games Count: "تم العثور على X لعبة"
```

**التصميم:**
- خلفية داكنة `#1E1E1E`
- Padding: 40px
- Border-radius: 12px
- Text-align: center
- Border: `#333`

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333`
- Title: يأخذ من `--theme-heading-1-color` (بلوكسي)
- Count: `#b0b0b0`
- Shadow: `0 2px 10px rgba(0, 0, 0, 0.3)`

---

#### 2. Filters Section (قسم الفلاتر)
```
├── Search Input (بحث)
├── Game Type (نوع اللعبة)
├── Game Status (حالة اللعبة)
├── Game Platform (المنصة)
├── Game Mode (طريقة اللعب)
├── Game Engine (محرك اللعبة)
└── Filter Button + Reset Button
```

**التصميم:**
- Flexbox layout مع wrap
- كل العناصر بنفس الارتفاع: 46px
- Gap: 15px بين العناصر
- خلفية داكنة `#1E1E1E`
- Border-radius: 12px
- Border: `#333`

**الحقول:**
- Background: `#252525` (داكن)
- Border: 1px solid #333
- Color: `#e0e0e0`
- Height: 46px
- Padding: 0 15px
- Border-radius: 8px
- Focus: border يتحول للون الأزرق `var(--theme-link-color)`

**الأزرار:**
- Height: 46px
- Padding: 0 30px
- Display: inline-flex
- Align-items: center
- Min-width: 120px
- Border-radius: 8px
- Font-weight: 600
- Transition: all 0.3s ease
- Filter Button: `<button type="submit">` - أزرق
- Reset Button: `<button type="button">` - أحمر
- Hover Effect: translateY(-2px) + box-shadow
- كلا الزرين الآن `<button>` لتنسيق موحد

**الألوان:**
- Background: `#1E1E1E` (داكن)
- Border: `#333`
- Filter Button: `var(--theme-link-color, #0073aa)`
- Reset Button: `#f44336`
- Shadow: `0 2px 10px rgba(0, 0, 0, 0.3)`

**Responsive:**
- Desktop: كل العناصر في صف واحد مع wrap
- Mobile: كل عنصر في صف

---

#### 3. Games Grid (شبكة الألعاب)
```
└── 4 أعمدة × 3 صفوف = 12 لعبة في الصفحة
```

**التصميم:**
- Grid: `repeat(4, 1fr)`
- Gap: 30px
- Cards مع border و shadow

**تصميم البطاقة (Game Card):**

```
┌─────────────────────┐
│ 📷 الصورة           │ ← 220px height
│    [2.7/10 ⭐]      │ ← التقييم فوق الصورة
├─────────────────────┤
│ العنوان (كبير)      │
│ [Anime MMO] [Tag]   │ ← Tags بلون أزرق فاتح
└─────────────────────┘
```

**العناصر:**

1. **الصورة:**
   - Height: 220px
   - Object-fit: cover
   - Hover: scale(1.1)
   - Position: relative

2. **التقييم (فوق الصورة):**
   - Position: absolute
   - Top: 12px, Right: 12px
   - Background: `rgba(30, 30, 30, 0.95)` (داكن شفاف)
   - Padding: 8px 12px
   - Border-radius: 12px
   - Border: `1px solid rgba(255, 255, 255, 0.1)`
   - Color: `#ffffff` (أبيض)
   - Text-shadow: `0 2px 4px rgba(0, 0, 0, 0.5)`
   - Backdrop-filter: `blur(10px)`
   - Box-shadow: `0 4px 15px rgba(0, 0, 0, 0.5)`
   - واضح جداً على أي صورة!

3. **العنوان:**
   - Font-size: 1.15em
   - Font-weight: 700
   - Margin-bottom: 15px
   - Color: يأخذ من `--theme-heading-3-color` (بلوكسي)
   - Fallback: `#e0e0e0`
   - Hover: يتحول للون الأزرق

4. **Tags:**
   - Background: `rgba(0, 115, 170, 0.2)` (شفاف)
   - Color: `var(--theme-link-color, #0073aa)`
   - Border-radius: 8px
   - Padding: 5px 12px
   - Font-weight: 600
   - قابل للنقر - يؤدي للفلترة حسب النوع

**Card Hover:**
- Transform: translateY(-8px)
- Box-shadow: `0 12px 35px rgba(0, 0, 0, 0.4)`
- Border-color: أزرق

**الألوان:**
- Card Background: `#1E1E1E` (داكن)
- Border: `#333`
- Border-radius: 12px
- Hover Border: `var(--theme-link-color, #0073aa)`
- Hover Shadow: `0 12px 35px rgba(0, 0, 0, 0.4)`

**Responsive:**
- Desktop (>1024px): 4 أعمدة
- Tablet (≤1024px): 3 أعمدة
- Mobile (≤768px): 2 أعمدة

**Pagination:**
- Flexbox layout
- Centered
- Gap: 10px
- Previous/Next buttons

---

## 🎨 المتغيرات المستخدمة (CSS Variables)

### من ثيم Blocksy Pro:

**الخطوط:**
```css
--theme-font-family              /* الخط العام */
--theme-heading-font-family      /* خط العناوين العام */
--theme-heading-1-font          /* خط H1 محدد */
--theme-heading-2-font          /* خط H2 محدد */
--theme-heading-3-font          /* خط H3 محدد */
--theme-headings-font-family    /* احتياطي للعناوين */
```

**الألوان:**
```css
--theme-text-color              /* لون النص العام */
--theme-heading-color           /* لون العناوين العام */
--theme-heading-1-color         /* لون H1 محدد */
--theme-heading-2-color         /* لون H2 محدد */
--theme-heading-3-color         /* لون H3 محدد */
--theme-headings-color          /* احتياطي للعناوين */
--theme-link-color              /* لون الروابط */
--theme-link-hover-color        /* لون الروابط عند hover */
--theme-background-color        /* لون الخلفية */
--theme-palette-color-3         /* لون من palette الثيم */
```

**التكامل:**
- ✅ كل العناوين تأخذ ألوانها وخطوطها من بلوكسي تلقائياً
- ✅ نظام احتياطي متعدد المستويات
- ✅ H1 للعناوين الرئيسية (عنوان اللعبة، عنوان الأرشيف)
- ✅ H2 لعناوين الأقسام (Game Info, Features, Review, etc.)
- ✅ H3 لعناوين البطاقات (Related News, Archive Cards)

---

## 📱 Responsive Breakpoints

```css
/* Tablet */
@media (max-width: 1024px) {
    - Features: 2 أعمدة
    - Ratings: 2 أعمدة
    - Games Grid: 3 أعمدة
}

/* Mobile */
@media (max-width: 768px) {
    - Features: عمود واحد
    - Ratings: عمود واحد
    - Games Grid: عمودين
    - Gallery: عمود واحد
    - Info Grid: عمود واحد
}
```

---

## 🎯 التأثيرات والحركات (Effects & Animations)

### Hover Effects:
```css
transform: translateY(-3px)
box-shadow: 0 6px 20px rgba(...)
border-color: change
```

### Transitions:
```css
transition: all 0.3s ease
transition: border-color 0.3s ease
transition: transform 0.3s ease
transition: width 0.6s ease (progress bars)
```

---

## 🌐 RTL Support

### صفحة اللعبة:
- Features checkmark ينتقل من اليسار لليمين
- Padding يتبادل (left ↔ right)
- Text-align: right

### صفحة الأرشيف:
- الفلاتر تعمل تلقائياً مع RTL
- Border direction ينعكس

---

## 🎨 الألوان الأساسية (Color Palette)

### Primary Colors:
- **الأزرق الرئيسي:** `#0073aa` (من Blocksy)
- **الأزرق الداكن:** `#005a87` (hover)
- **البنفسجي:** `#667eea` (gradients)
- **البنفسجي الغامق:** `#764ba2` (gradients)

### Dark Theme Colors:
- **خلفية البطاقات:** `#1E1E1E` (رمادي داكن)
- **حدود البطاقات:** `#333` (رمادي داكن)
- **نص فاتح رئيسي:** `#e0e0e0`
- **نص فاتح ثانوي:** `#b0b0b0`
- **نص فاتح خفيف:** `#a0a0a0`
- **ظلال داكنة:** `rgba(0, 0, 0, 0.3)` - `rgba(0, 0, 0, 0.4)`

### Accent Colors:
- **أحمر (Reset):** `#f44336`
- **أخضر (Success):** متوافق مع الثيم

---

## 📦 المكونات القابلة لإعادة الاستخدام

### Info Card:
```css
.info-item {
    background: #1E1E1E;  /* داكن */
    padding: 20px;
    border-radius: 12px;
    border: 1px solid #333;
    border-left: 4px solid var(--theme-link-color);
    color: #e0e0e0;  /* فاتح */
}
```

### Feature Card:
```css
.game-features-list li {
    background: #1E1E1E;  /* داكن */
    padding: 20px 24px 20px 55px;
    border: 1px solid #333;
    border-radius: 12px;
    position: relative;
    color: #e0e0e0;  /* فاتح */
}
```

### Rating Card:
```css
.rating-item {
    background: #1E1E1E;  /* داكن */
    padding: 24px;
    border-radius: 12px;
    border: 1px solid #333;
    color: #e0e0e0;  /* فاتح */
}
```

### Button:
```css
.filter-button {
    height: 46px;
    padding: 0 30px;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.3s ease;
}
```

---

## ✨ الميزات المميزة

### 1. Progress Bars في التقييمات:
- متحركة عند التحميل
- Gradient ملون
- Width محسوب من التقييم (rating × 10%)

### 2. Gradient Backgrounds:
- Overall Rating Background: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
- Checkmarks: `linear-gradient(135deg, #0073aa 0%, #667eea 100%)`
- Progress Bars: `linear-gradient(90deg, #0073aa 0%, #667eea 100%)`

### 3. Shadow Effects:
- Cards: shadows خفيفة
- Hover: shadows أقوى
- Overall Rating: shadow ملون

### 4. Icon System:
- Emojis للتقييمات (📖🎮🎨🎵⭐)
- ✓ للمميزات
- Font icons متوافقة مع الثيم

---

## 🔧 ملاحظات التطوير

### الأمان:
- جميع البيانات sanitized
- Nonce verification
- Capability checks

### الأداء:
- CSS محسّن
- لا يوجد JavaScript زائد
- Images lazy loading (من الثيم)

### التوافق:
- WordPress 6.4+
- PHP 8.0+
- Blocksy Theme
- RTL Support كامل

---

## 📝 التحديثات المستقبلية

### مقترحة:
- [ ] Ajax filtering في الأرشيف
- [ ] Sorting options
- [ ] View switcher (Grid/List)
- [ ] User ratings system
- [ ] Favorites system
- [ ] Compare games feature

---

## 🎨 التصميم الداكن (Dark Design)

### الفلسفة:
الإضافة تستخدم تصميم داكن احترافي (`#1E1E1E`) لجميع البطاقات والعناصر:

**المميزات:**
- ✅ مريح للعين في الاستخدام الطويل
- ✅ يبرز المحتوى والصور
- ✅ يتكامل مع الثيمات الداكنة
- ✅ تباين ممتاز مع النصوص الفاتحة
- ✅ ظلال داكنة قوية للعمق

**التطبيق:**
- كل البطاقات: `#1E1E1E`
- الحدود: `#333`
- النصوص: `#e0e0e0` (رئيسي)، `#b0b0b0` (ثانوي)
- الظلال: `rgba(0, 0, 0, 0.3-0.5)`

---

**آخر تحديث:** 2025-10-03
**الإصدار:** 1.0.0
**التصميم:** Dark Theme with Blocksy Pro Integration
**اسم الإضافة:** MMOARAB Core

**الإصدار الأول يتضمن:**
- نظام تقييمات متقدم مع Progress Bars
- معرض صور مع Lightbox تفاعلي
- نظام تعليقات متكامل مع تصميم داكن
- أرشيف مع فلاتر متقدمة (6 فلاتر)
- تكامل كامل مع Blocksy Pro
- لوحة تحكم منفصلة (MMOARAB Core Dashboard)
