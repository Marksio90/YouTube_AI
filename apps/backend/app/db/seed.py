"""
Seed script — realistic demo data for AI Media OS.

Run:  python -m app.db.seed
      make seed  (inside backend container)

Idempotent: deletes seed user (CASCADE handles rest) then recreates.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone

import structlog
from passlib.context import CryptContext
from sqlalchemy import delete

from app.db.models.analytics import AnalyticsSnapshot, SnapshotType
from app.db.models.brief import Brief, BriefStatus
from app.db.models.channel import Channel, ChannelStatus
from app.db.models.compliance import (
    CheckMode, CheckStatus, ComplianceCheck,
    FlagSource, RiskCategory, RiskFlag, RiskSeverity,
)
from app.db.models.monetization import (
    AffiliateLink, AffiliatePlatform, RevenueSource, RevenueStream,
)
from app.db.models.performance import (
    PerformanceScore, Recommendation,
    RecommendationPriority, RecommendationSource,
    RecommendationStatus, RecommendationType,
)
from app.db.models.pipeline import (
    Pipeline, PipelineRun, PipelineRunStatus, PipelineStepResult,
)
from app.db.models.publication import (
    Publication, PublicationStatus, PublicationVisibility,
)
from app.db.models.script import Script, ScriptStatus, ScriptTone
from app.db.models.topic import Topic, TopicSource, TopicStatus
from app.db.models.user import User, UserRole
from app.db.models.workflow import (
    JobStatus, RunStatus,
    WorkflowAuditEvent, WorkflowJob, WorkflowRun,
)
from app.db.session import AsyncSessionLocal

log = structlog.get_logger(__name__)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
random.seed(42)

# ── Time helpers ───────────────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc)
TODAY = date.today()


def dt(days_ago: int, hour: int = 12) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0,
    )


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


# ── Pre-generated UUIDs (stable cross-section references) ─────────────────────
UID = {k: uuid.uuid4() for k in [
    "user",
    "ch_tech", "ch_finance", "ch_fit",
    *[f"topic_{i}" for i in range(1, 21)],
    *[f"brief_{i}" for i in range(1, 11)],
    *[f"script_{i}" for i in range(1, 11)],
    *[f"pub_{i}" for i in range(1, 11)],
    *[f"check_{i}" for i in range(1, 11)],
    "pipe_full", "pipe_quick",
    "run_tech1", "run_fin1", "run_fit1", "run_tech2",
]}


# ── User & Channels ────────────────────────────────────────────────────────────

async def seed_user(db) -> None:
    user = User(
        id=UID["user"],
        email="demo@aimediaos.com",
        name="Demo Account",
        hashed_password=pwd_ctx.hash("demo1234"),
        role=UserRole.owner,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    log.info("seed.user.done")


async def seed_channels(db) -> None:
    channels = [
        Channel(
            id=UID["ch_tech"],
            owner_id=UID["user"],
            youtube_channel_id="UCtech_insider_pl_2024",
            name="TechInsider PL",
            handle="@techinsiderpl",
            niche="Technologia i AI",
            status=ChannelStatus.active,
            subscriber_count=45230,
            view_count=2100000,
            video_count=87,
            monetization_enabled=True,
        ),
        Channel(
            id=UID["ch_finance"],
            owner_id=UID["user"],
            youtube_channel_id="UCfinanse_praktyczne_2024",
            name="Finanse Praktyczne",
            handle="@finansepraktyczne",
            niche="Finanse Osobiste",
            status=ChannelStatus.active,
            subscriber_count=28450,
            view_count=1400000,
            video_count=62,
            monetization_enabled=True,
        ),
        Channel(
            id=UID["ch_fit"],
            owner_id=UID["user"],
            youtube_channel_id="UCfitlife_daily_2024",
            name="FitLife Daily",
            handle="@fitlifedaily",
            niche="Fitness i Zdrowie",
            status=ChannelStatus.active,
            subscriber_count=15820,
            view_count=680000,
            video_count=45,
            monetization_enabled=False,
        ),
    ]
    for ch in channels:
        db.add(ch)
    await db.flush()
    log.info("seed.channels.done", count=3)


# ── Topics ─────────────────────────────────────────────────────────────────────

_TOPICS = [
    # TechInsider PL (7)
    (1, "ch_tech", "Jak AI zmienia rynek pracy w 2025 roku", "Analiza wpływu sztucznej inteligencji na zatrudnienie w Polsce i Europie.", ["AI", "rynek pracy", "automatyzacja", "przyszłość pracy"], 8.7, TopicSource.ai_suggested, TopicStatus.briefed),
    (2, "ch_tech", "Claude vs GPT-4o — który model jest lepszy?", "Szczegółowe porównanie możliwości modeli językowych Anthropic i OpenAI.", ["Claude", "GPT-4o", "LLM", "AI comparison"], 9.1, TopicSource.trending, TopicStatus.briefed),
    (3, "ch_tech", "Python czy Rust — co wybrać do projektu?", "Przewodnik po wyborze języka programowania w 2025 roku.", ["Python", "Rust", "programowanie", "wydajność"], 7.2, TopicSource.manual, TopicStatus.briefed),
    (4, "ch_tech", "Budowanie agentów AI z LangChain krok po kroku", "Tutorial tworzenia autonomicznych agentów AI przy użyciu frameworka LangChain.", ["LangChain", "agent AI", "tutorial", "automatyzacja"], 8.5, TopicSource.ai_suggested, TopicStatus.briefed),
    (5, "ch_tech", "Top 10 narzędzi AI dla programistów w 2025", "Przegląd najlepszych narzędzi wspomaganych AI dla deweloperów.", ["AI tools", "GitHub Copilot", "produktywność", "narzędzia"], 8.9, TopicSource.trending, TopicStatus.new),
    (6, "ch_tech", "Bezpieczeństwo danych w erze generatywnego AI", "Jak chronić dane osobowe i firmowe w dobie LLM i RAG.", ["cybersecurity", "AI safety", "RODO", "dane"], 7.8, TopicSource.ai_suggested, TopicStatus.new),
    (7, "ch_tech", "Quantum computing wyjaśniony dla laika", "Podstawy obliczeń kwantowych bez matematyki.", ["quantum", "IBM", "Google", "fizyka"], 6.3, TopicSource.manual, TopicStatus.archived),
    # Finanse Praktyczne (7)
    (8, "ch_finance", "Jak zacząć inwestować 500 zł miesięcznie", "Praktyczny przewodnik inwestowania małych kwot na GPW i ETF.", ["inwestowanie", "ETF", "GPW", "500 zł"], 9.3, TopicSource.trending, TopicStatus.briefed),
    (9, "ch_finance", "ETF vs fundusze aktywne — gdzie są twoje pieniądze?", "Porównanie kosztów i wyników ETF-ów oraz funduszy zarządzanych aktywnie.", ["ETF", "fundusze inwestycyjne", "koszty", "TER"], 8.6, TopicSource.ai_suggested, TopicStatus.briefed),
    (10, "ch_finance", "Podatek Belki — jak legalnie ograniczyć straty", "Strategie podatkowe dla inwestorów giełdowych w Polsce.", ["podatek Belki", "IKE", "IKZE", "optymalizacja podatkowa"], 8.2, TopicSource.manual, TopicStatus.briefed),
    (11, "ch_finance", "FIRE movement — jak przejść na emeryturę w 40 lat", "Strategia finansowej niezależności i wczesnej emerytury.", ["FIRE", "niezależność finansowa", "oszczędności", "emerytura"], 7.9, TopicSource.ai_suggested, TopicStatus.briefed),
    (12, "ch_finance", "Czy warto inwestować w złoto w 2025 roku?", "Analiza złota jako aktywa w portfelu inwestycyjnym.", ["złoto", "hedge", "inflacja", "aktywa"], 7.5, TopicSource.trending, TopicStatus.new),
    (13, "ch_finance", "Dywidendy — 5 spółek GPW płacących regularnie", "Analiza dywidendowych spółek notowanych na warszawskiej giełdzie.", ["dywidendy", "GPW", "spółki", "dochód pasywny"], 7.1, TopicSource.manual, TopicStatus.new),
    (14, "ch_finance", "Budżet domowy — metoda 50/30/20 w praktyce", "Jak stosować metodę budżetowania 50/30/20 w polskich realiach.", ["budżet", "oszczędzanie", "finanse osobiste", "metoda"], 8.4, TopicSource.ai_suggested, TopicStatus.researching),
    # FitLife Daily (6)
    (15, "ch_fit", "Plan treningowy dla początkujących — 12 tygodni", "Kompletny program siłowy dla osób zaczynających swoją przygodę z treningiem.", ["trening siłowy", "początkujący", "plan treningowy", "siłownia"], 8.8, TopicSource.manual, TopicStatus.briefed),
    (16, "ch_fit", "Post przerywany IF — czy naprawdę działa?", "Naukowe spojrzenie na intermittent fasting i jego wpływ na odchudzanie.", ["IF", "post przerywany", "odchudzanie", "nauka"], 8.3, TopicSource.trending, TopicStatus.briefed),
    (17, "ch_fit", "5 błędów w bieganiu niszczących kolana", "Najczęstsze błędy techniki biegu prowadzące do kontuzji kolan.", ["bieganie", "kontuzje", "kolano", "technika biegu"], 7.6, TopicSource.ai_suggested, TopicStatus.briefed),
    (18, "ch_fit", "Suplementacja — co naprawdę działa według nauki", "Przegląd popularnych suplementów i badań naukowych ich dotyczących.", ["suplementy", "kreatyna", "białko", "nauka"], 7.9, TopicSource.ai_suggested, TopicStatus.new),
    (19, "ch_fit", "Sen i regeneracja — dlaczego 8 godzin to mit", "Jak poprawić jakość snu i regenerację mięśni po treningu.", ["sen", "regeneracja", "cortisol", "HRV"], 8.1, TopicSource.manual, TopicStatus.researching),
    (20, "ch_fit", "Trening w domu bez sprzętu — 30 minut dziennie", "Kompletny program ćwiczeń z własną masą ciała na każdy poziom.", ["trening w domu", "calisthenics", "bez sprzętu", "30 minut"], 9.0, TopicSource.trending, TopicStatus.briefed),
]

_CH_MAP = {"ch_tech": UID["ch_tech"], "ch_finance": UID["ch_finance"], "ch_fit": UID["ch_fit"]}


async def seed_topics(db) -> None:
    for i, ch_key, title, desc, kw, score, src, status in _TOPICS:
        db.add(Topic(
            id=UID[f"topic_{i}"],
            channel_id=_CH_MAP[ch_key],
            title=title,
            description=desc,
            keywords=kw,
            trend_score=score,
            source=src,
            status=status,
        ))
    await db.flush()
    log.info("seed.topics.done", count=len(_TOPICS))


# ── Briefs ─────────────────────────────────────────────────────────────────────

_BRIEFS = [
    (1, "ch_tech",    "topic_1",  "Wpływ AI na polski rynek pracy 2025",          "Specjaliści IT, menedżerowie HR, studenci ostatnich lat",     ["AI", "rynek pracy", "automatyzacja"], 780),
    (2, "ch_tech",    "topic_2",  "Claude 3.5 vs GPT-4o — test na żywym organizmie", "Programiści i entuzjaści AI szukający najlepszego modelu",  ["LLM", "Claude", "GPT-4o", "benchmark"], 900),
    (3, "ch_tech",    "topic_4",  "Twój pierwszy agent AI z LangChain",            "Programiści Python ze znajomością podstaw ML",               ["LangChain", "Python", "agent", "LLM"], 1200),
    (4, "ch_finance", "topic_8",  "Inwestowanie 500 zł miesięcznie — start guide", "Osoby 25-40 lat zaczynające inwestować",                    ["ETF", "inwestowanie", "GPW", "początkujący"], 720),
    (5, "ch_finance", "topic_9",  "ETF vs fundusze aktywne — analiza 10 lat",      "Inwestorzy z doświadczeniem 1-3 lat",                       ["ETF", "fundusze", "koszty", "wyniki"], 840),
    (6, "ch_finance", "topic_10", "Podatek Belki — legalne strategie 2025",        "Inwestorzy giełdowi rozliczający podatki",                  ["podatek", "IKE", "IKZE", "strategie"], 660),
    (7, "ch_finance", "topic_11", "FIRE w Polsce — czy to możliwe?",               "Osoby 28-45 lat zainteresowane wolnością finansową",        ["FIRE", "oszczędności", "inwestycje", "emerytura"], 780),
    (8, "ch_fit",     "topic_15", "12-tygodniowy plan treningowy dla początkujących", "Osoby 20-40 lat bez doświadczenia siłowego",             ["trening", "siłownia", "plan", "początkujący"], 900),
    (9, "ch_fit",     "topic_16", "Intermittent Fasting — co mówi nauka",          "Osoby chcące schudnąć lub poprawić zdrowie metaboliczne",  ["IF", "dieta", "nauka", "odchudzanie"], 780),
    (10, "ch_fit",    "topic_20", "30-minutowy trening w domu — plan dla każdego", "Osoby bez dostępu do siłowni lub z ograniczonym czasem",   ["dom", "trening", "ćwiczenia", "bez sprzętu"], 720),
]


async def seed_briefs(db) -> None:
    for i, ch_key, topic_key, title, audience, kw, dur in _BRIEFS:
        db.add(Brief(
            id=UID[f"brief_{i}"],
            channel_id=_CH_MAP[ch_key],
            topic_id=UID[topic_key],
            title=title,
            target_audience=audience,
            key_points=[
                {"point": f"Kluczowy punkt {j+1} dla {title[:30]}..."}
                for j in range(4)
            ],
            seo_keywords=kw,
            estimated_duration_seconds=dur,
            tone="educational",
            status=BriefStatus.approved,
        ))
    await db.flush()
    log.info("seed.briefs.done", count=len(_BRIEFS))


# ── Scripts ────────────────────────────────────────────────────────────────────

_SCRIPTS = [
    dict(
        idx=1, ch="ch_tech", brief="brief_1",
        title="Jak AI zmienia rynek pracy w 2025 roku — fakty i liczby",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=87.5, compliance_score=92.0,
        keywords=["AI", "rynek pracy", "automatyzacja", "przyszłość pracy"],
        hook="W ciągu ostatnich 12 miesięcy zautomatyzowano 3,5 miliona stanowisk pracy w Polsce. Ale to nie jest apokalipsa — to rewolucja, na której możesz zarobić. Zostań do końca, bo pokażę ci konkretne dane i strategie.",
        body="""Analiza 200 raportów z 2024 roku pokazuje jednoznacznie: AI nie eliminuje pracy — przesuwa ją. Stanowiska najbardziej zagrożone to te oparte na rutynowych, powtarzalnych zadaniach: wprowadzanie danych, podstawowa obsługa klienta, proste analizy finansowe.

Co rośnie? Zapotrzebowanie na prompt engineerów wzrosło o 847% rok do roku według LinkedIn. Analitycy danych zarabiają średnio o 34% więcej niż rok temu. Architekci systemów AI zarabiają od 25 do 45 tysięcy złotych miesięcznie.

Które sektory są bezpieczne? Zawody wymagające empatii, kreatywności i myślenia krytycznego. Psychologowie, pielęgniarki, architekci, nauczyciele — tu AI jest asystentem, nie zastępcą. McKinsey szacuje, że do 2030 roku 12 milionów pracowników zmieni zawód. Pytanie brzmi: czy będziesz wśród tych, którzy na tym skorzystają, czy wśród tych, którzy zostaną w tyle?""",
        cta="Jeśli chcesz wiedzieć, które konkretnie umiejętności chronią przed automatyzacją, napisz 'lista' w komentarzu. Subskrybuj, żeby nie przegapić kolejnego odcinka o AI.",
    ),
    dict(
        idx=2, ch="ch_tech", brief="brief_2",
        title="Claude 3.5 Sonnet vs GPT-4o — 30-dniowy test w prawdziwej pracy",
        tone=ScriptTone.controversial, status=ScriptStatus.approved,
        seo_score=91.2, compliance_score=88.5,
        keywords=["Claude", "GPT-4o", "LLM", "AI comparison", "Anthropic"],
        hook="Przez 30 dni używałem wyłącznie Claude 3.5 Sonnet i GPT-4o do codziennej pracy programisty. Wyniki mnie zaskoczyły — i prawdopodobnie zaskoczyłyby też ciebie.",
        body="""Test obejmował 847 zadań: pisanie kodu, debugowanie, tłumaczenia techniczne, analiza dokumentacji i tworzenie treści. Każde zadanie oceniałem według tych samych kryteriów: poprawność, szybkość i użyteczność odpowiedzi.

Kodowanie: Claude wygrał w 68% przypadków, szczególnie przy złożonych refaktoryzacjach i wyjaśnianiu architektury systemów. GPT-4o był lepszy przy generowaniu boilerplate i integracji z pluginami. Pisanie treści: Claude brzmi bardziej naturalnie po polsku i angielsku. GPT-4o generuje treści szybciej, ale wymaga więcej edycji.

Kontekst i pamięć: tu Claude ma miażdżącą przewagę z oknem kontekstowym 200K tokenów. Dla długich projektów to game changer — wrzucasz cały codebase i model rozumie zależności. Cena: GPT-4o jest tańszy przy małych wolumenach. Claude opłaca się od ~100 tys. tokenów dziennie.

Mój werdykt? Dla programistów i analityków — Claude. Dla content creatorów i małych projektów — GPT-4o. Najlepsza strategia: używaj obu.""",
        cta="Który model ty preferujesz? Napisz w komentarzu. Daj suba jeśli chcesz więcej takich testów.",
    ),
    dict(
        idx=3, ch="ch_tech", brief="brief_3",
        title="Twój pierwszy agent AI z LangChain — tutorial krok po kroku",
        tone=ScriptTone.educational, status=ScriptStatus.review,
        seo_score=83.7, compliance_score=90.0,
        keywords=["LangChain", "Python", "agent AI", "tutorial", "LLM"],
        hook="Za 20 minut będziesz mieć działającego agenta AI, który przeszukuje internet, analizuje dane i wykonuje zadania autonomicznie. Potrzebujesz tylko Pythona i klucza API.",
        body="""LangChain to framework, który łączy modele językowe z zewnętrznymi narzędziami. Agent AI to program, który sam decyduje, których narzędzi użyć, żeby osiągnąć cel.

Zaczynamy od instalacji: pip install langchain langchain-openai tavily-python. Klucze API: OpenAI i Tavily (darmowy tier wystarczy). Definiujemy narzędzia — w tym przypadku: wyszukiwarka internetowa i kalkulator. Agent decyduje sam, kiedy ich użyć.

Kluczowa koncepcja: ReAct pattern. Agent myśli (Thought), decyduje o akcji (Action), obserwuje wynik (Observation) i powtarza, aż osiągnie cel. To eliminuje potrzebę twardego kodowania każdego scenariusza. W kodzie używamy AgentExecutor z verbose=True — dzięki temu widzisz każdy krok rozumowania agenta. Idealne do debugowania i nauki.""",
        cta="Kod z tego tutorialu znajdziesz na GitHubie — link w opisie. Subskrybuj, żeby nie przegapić kolejnej części o pamięci agentów.",
    ),
    dict(
        idx=4, ch="ch_finance", brief="brief_4",
        title="Inwestowanie 500 zł miesięcznie — kompletny przewodnik dla początkujących",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=94.1, compliance_score=91.5,
        keywords=["inwestowanie", "ETF", "GPW", "500 zł", "początkujący"],
        hook="Jeśli masz 500 złotych miesięcznie i nie wiesz, co z nimi zrobić — ten film jest dla ciebie. Po 10 minutach będziesz wiedział, jak zacząć inwestować bez wiedzy i bez maklerskiego konta za 5000 złotych.",
        body="""Najpierw zasada: zanim zaczniesz inwestować, miej poduszkę finansową — 3-6 miesięcy wydatków na koncie oszczędnościowym. Bez tego inwestowanie to ruletka. Zakładam, że masz poduszkę. Co dalej?

Krok 1: Otwórz konto IKE lub IKZE. To legalna tarcza podatkowa — nie płacisz 19% podatku Belki od zysku. Limit wpłat IKE w 2025 to 23 472 zł rocznie. Krok 2: Wybierz globalny ETF. Polecam MSCI World lub S&P 500 — kupujesz kawałek 1500-3000 największych firm świata. Historycznie 8-10% rocznie. Krok 3: Ustaw zlecenie stałe. 500 zł, co miesiąc, ten sam dzień. Bez emocji, bez analizowania newsów.

Za 30 lat, przy 500 zł miesięcznie i 8% zysku rocznie, będziesz mieć 745 000 złotych. Nie dlatego, że trafiłeś w odpowiedni moment rynku — dlatego, że byłeś konsekwentny.""",
        cta="Jeśli chcesz szczegółowy ranking kont IKE i IKZE z aktualnymi opłatami, napisz 'ranking' w komentarzu. Subskrybuj po więcej wiedzy o finansach.",
    ),
    dict(
        idx=5, ch="ch_finance", brief="brief_5",
        title="ETF vs fundusze aktywne — 10 lat danych które zmienią twoje myślenie",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=88.3, compliance_score=93.0,
        keywords=["ETF", "fundusze inwestycyjne", "koszty", "TER", "indeks"],
        hook="87% aktywnie zarządzanych funduszy przegrywa z rynkiem w perspektywie 10 lat. Masz pieniądze w funduszu aktywnym? Sprawdź, ile naprawdę tracisz.",
        body="""Dane ze SPIVA (S&P Indices vs Active) za ostatnie 10 lat są jednoznaczne: w horyzoncie 10-letnim 87,4% funduszy akcyjnych przegrywa benchmark. Dlaczego? Koszty.

Typowy fundusz aktywny w Polsce pobiera 2-2,5% rocznie (TER + opłata manipulacyjna). ETF: 0,07-0,25% rocznie. Różnica 2% rocznie przez 30 lat na 100 000 zł to 220 000 zł utopionego kapitału. To nie pomyłka — to ćwierć miliona złotych.

Kontrargument: a co z funduszami, które biją rynek? Istnieją, ale nie możesz ich z góry wskazać. Fundusz, który wygrał ostatnie 5 lat, statystycznie nie wygra kolejnych 5. To mean reversion — fundamentalne prawo rynku. Wyjątki istnieją (Berkshire Hathaway, Fundsmith), ale są to wyjątki potwierdzające regułę i wymagają samodzielnej analizy.""",
        cta="Powiedz mi w komentarzu — masz pieniądze w funduszach aktywnych czy ETF-ach? Subskrybuj, za tydzień wideo o tym, jak wybrać najlepszy ETF na GPW.",
    ),
]

_SCRIPTS += [
    dict(
        idx=6, ch="ch_finance", brief="brief_6",
        title="Podatek Belki w 2025 — 5 legalnych sposobów na zmniejszenie podatku",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=85.6, compliance_score=94.5,
        keywords=["podatek Belki", "IKE", "IKZE", "optymalizacja podatkowa"],
        hook="Płacisz 19% podatku od każdego zysku giełdowego? Istnieje 5 całkowicie legalnych sposobów, żeby to zmienić. Wiele osób o nich nie wie — i traci tysiące złotych rocznie.",
        body="""Podatek Belki to 19% od zysku kapitałowego. Dotyczy dywidend, odsetek i zysku ze sprzedaży papierów wartościowych. W 2024 roku Polacy zapłacili z tego tytułu ponad 3 miliardy złotych.

Metoda 1: IKE (Indywidualne Konto Emerytalne). Wpłaty do 23 472 zł rocznie. Wypłata po 60. roku życia — zero podatku. Metoda 2: IKZE (Indywidualne Konto Zabezpieczenia Emerytalnego). Limit 8 322 zł. Bonus: odliczenie od podstawy opodatkowania — oszczędzasz 12-32% rocznie na PIT. Metoda 3: Tax loss harvesting. Sprzedajesz stratne pozycje przed końcem roku, żeby skompensować zyski. Legalne i skuteczne. Metoda 4: Przeniesienie aktywów do spółki. Dla inwestorów z portfelem powyżej 300 tys. zł — opodatkowanie CIT 9% zamiast 19%. Metoda 5: Konta zagraniczne w UE — w niektórych przypadkach korzystniejsze umowy o unikaniu podwójnego opodatkowania.""",
        cta="Który sposób już stosujesz? Napisz w komentarzu. Jeśli chcesz kalkulator IKE vs IKZE, link w opisie.",
    ),
    dict(
        idx=7, ch="ch_finance", brief="brief_7",
        title="FIRE movement w Polsce — czy wolność finansowa jest możliwa?",
        tone=ScriptTone.inspirational, status=ScriptStatus.approved,
        seo_score=82.4, compliance_score=89.0,
        keywords=["FIRE", "niezależność finansowa", "oszczędności", "emerytura", "wolność"],
        hook="Mam 38 lat i nie muszę już pracować dla pieniędzy. Nie dlatego, że odziedziczyłem majątek — dlatego, że przez 12 lat stosowałem jedną prostą strategię. Dzisiaj ci ją pokazuję.",
        body="""FIRE to skrót od Financial Independence, Retire Early. Nie chodzi o to, żeby przestać pracować w sensie dosłownym — chodzi o to, żebyś pracował, bo chcesz, nie dlatego, że musisz.

Reguła 4%: jeśli twoje roczne wydatki to X, potrzebujesz 25X zainwestowanego kapitału. Przy 4% stopie wypłaty portfel historycznie wytrzymuje 30+ lat bez uszczuplenia. Przy wydatkach 5000 zł miesięcznie (60 000 zł rocznie) potrzebujesz 1 500 000 zł. Brzmi nieosiągalnie? Przy stopie oszczędności 50% i zarobkach 8000 zł netto — osiągasz ten cel w 17 lat.

Kluczowe etapy: FI ratio (procent pokrycia wydatków przez inwestycje), Coast FIRE (punkt, w którym możesz przestać aktywnie inwestować i pozwolić procentowi składanemu działać), Barista FIRE (częściowa praca przy pasywnym dochodzie). Polski kontekst: niższe koszty życia niż w USA oznaczają niższy target. Warszawa jest droższa od małych miast 2-3x — lokalizacja ma ogromne znaczenie.""",
        cta="Ile wynosi twój FI ratio? Policz i napisz w komentarzu. Subskrybuj, żeby nie przegapić wideo o konkretnym planie inwestycyjnym FIRE.",
    ),
    dict(
        idx=8, ch="ch_fit", brief="brief_8",
        title="12-tygodniowy plan treningowy dla początkujących — zrób to raz porządnie",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=89.7, compliance_score=95.0,
        keywords=["trening siłowy", "początkujący", "plan treningowy", "siłownia"],
        hook="Większość planów treningowych dla początkujących jest złożona jak skład rakiety kosmicznej. Ten plan ma 4 ćwiczenia. Używają go osoby bez żadnego doświadczenia i widzą wyniki po 8 tygodniach.",
        body="""Program opiera się na 4 ruchach wielostawowych: przysiad, martwy ciąg, wyciskanie i wioślarstwo. To 80% wszystkich korzyści z treningu siłowego. Reszta to szczegóły.

Tygodnie 1-4 (adaptacja): 3 treningi tygodniowo, 3x8-10 powtórzeń każde ćwiczenie. Priorytet: technika nad ciężarem. Waga: zacznij od takiej, przy której ostatnie 2 powtórzenia są wymagające, ale forma nie siada. Tygodnie 5-8 (progresja): dodajesz 2,5-5 kg co tydzień, kiedy zakończysz wszystkie serie z dobrą techniką. To liniowa progresja — najprostszy i najskuteczniejszy model dla początkujących. Tygodnie 9-12 (konsolidacja): 3x5 ciężkich powtórzeń, deload (lżejszy tydzień) przed końcem programu.

Dieta: bez odpowiedniej podaży białka (1,6-2,2g/kg masy ciała) nie ma wzrostu mięśni. Reszta to detale. Nie musisz liczyć kalorii w fazie 1 i 2.""",
        cta="Cały plan w PDF do pobrania — link w opisie. Jeśli masz pytania o technikę, pisz w komentarzu. Subskrybuj dla kolejnych odcinków z programem.",
    ),
    dict(
        idx=9, ch="ch_fit", brief="brief_9",
        title="Post przerywany IF — co mówi nauka po 10 latach badań",
        tone=ScriptTone.educational, status=ScriptStatus.approved,
        seo_score=86.2, compliance_score=91.0,
        keywords=["IF", "post przerywany", "odchudzanie", "nauka", "insulin"],
        hook="Miliony ludzi stosują post przerywany. Ale czy naprawdę działa — i jeśli tak, to dlaczego? Przejrzałem 47 badań z ostatnich 10 lat. Oto co wiemy naprawdę.",
        body="""Intermittent fasting (IF) to nie dieta — to wzorzec jedzenia. Najbardziej popularne warianty: 16:8 (okno żywieniowe 8 godzin), 5:2 (dwa dni z ograniczoną kalorycznością do 500 kcal), OMAD (jeden posiłek dziennie).

Co badania potwierdzają? Utrata wagi: IF działa, ale głównie dlatego, że naturalnie ogranicza kalorie, nie dlatego, że ma magiczne właściwości. Metaanaliza z 2022 roku (27 badań, 4000 uczestników): IF i tradycyjna restrykcja kaloryczna dają podobne efekty. Insulinooporność: tutaj IF ma realną przewagę — 12-16 godzin postu obniża poziom insuliny i poprawia wrażliwość insulinową. Szczególnie ważne przy prediabetes. Zdrowie metaboliczne: markery stanu zapalnego (CRP, IL-6) poprawiają się, ale efekt jest skromny bez towarzyszącej utraty wagi.

Co NIE działa? Mit o "oknie anabolicznym" — pominięcie śniadania nie katabolizuje mięśni. Mit o "detoksie" — wątroba robi to 24/7, IF jej nie wspomaga w żaden szczególny sposób.""",
        cta="Stosujesz IF? Jaki wariant i jak ci idzie? Napisz w komentarzu. Subskrybuj, za 2 tygodnie wideo o tym, jak dieta wpływa na wyniki treningowe.",
    ),
    dict(
        idx=10, ch="ch_fit", brief="brief_10",
        title="30-minutowy trening w domu bez sprzętu — program na 8 tygodni",
        tone=ScriptTone.inspirational, status=ScriptStatus.approved,
        seo_score=93.5, compliance_score=96.0,
        keywords=["trening w domu", "calisthenics", "bez sprzętu", "30 minut"],
        hook="Nie masz czasu? Nie masz siłowni? Nie masz sprzętu? Dobra wiadomość: te 3 powody to wymówki, a nie przeszkody. Ten program zajmuje 30 minut i nie wymaga niczego poza twoim ciałem.",
        body="""Program oparty na 6 ćwiczeniach: pompki, przysiady, deski, podciąganie (na drążku lub drzwiach), dipy (na krześle) i burpees. Każde z nich angażuje wiele grup mięśniowych jednocześnie.

Struktura treningu: rozgrzewka 5 minut, blok siłowy 20 minut (3 obwody), rozciąganie 5 minut. Intensywność kontrolujesz przez tempo i warianty ćwiczeń — pompki na kolanach vs. diamondowe vs. z obciążeniem (plecak z książkami).

Tygodnie 1-2: poznaj ćwiczenia, skup się na technice, 2 treningi tygodniowo. Tygodnie 3-5: dodaj trzeci trening, zwiększ liczbę powtórzeń o 10-15% każdego tygodnia. Tygodnie 6-8: 4 treningi tygodniowo, dodaj trudniejsze warianty.

Postęp mierzony w liczbie powtórzeń, nie w kilogramach. Po 8 tygodniach typowy użytkownik robi 3-5x więcej niż na starcie. Bez jednej wizyty na siłowni.""",
        cta="Plan tygodniowy gotowy do wydruku czeka na ciebie w opisie. Napisz w komentarzu, od którego dnia zaczynasz — dam ci znać kiedy podesłać kolejną część.",
    ),
]


async def seed_scripts(db) -> None:
    for s in _SCRIPTS:
        db.add(Script(
            id=UID[f"script_{s['idx']}"],
            channel_id=_CH_MAP[s["ch"]],
            brief_id=UID[s["brief"]],
            title=s["title"],
            hook=s["hook"],
            body=s["body"],
            cta=s["cta"],
            keywords=s["keywords"],
            target_duration_seconds=720,
            tone=s["tone"],
            status=s["status"],
            seo_score=s["seo_score"],
            compliance_score=s["compliance_score"],
            version=1,
        ))
    await db.flush()
    log.info("seed.scripts.done", count=len(_SCRIPTS))


# ── Publications ───────────────────────────────────────────────────────────────

_PUBLICATIONS = [
    # published
    dict(idx=1, ch="ch_tech",    script=1, yt_id="aI2025_rynek",  title="Jak AI zmienia rynek pracy w 2025 roku — fakty i liczby", views=45200,  likes=2180, comments=312, revenue=135.40, pub_days_ago=45, dur=847),
    dict(idx=2, ch="ch_tech",    script=2, yt_id="claudeVSgpt4o", title="Claude 3.5 vs GPT-4o — 30-dniowy test w prawdziwej pracy",  views=62100,  likes=3820, comments=584, revenue=186.30, pub_days_ago=30, dur=934),
    dict(idx=4, ch="ch_finance", script=4, yt_id="invest500plZL",  title="Inwestowanie 500 zł miesięcznie — kompletny przewodnik",    views=89400,  likes=4210, comments=721, revenue=267.90, pub_days_ago=60, dur=782),
    dict(idx=5, ch="ch_finance", script=5, yt_id="ETFvsAktywne",  title="ETF vs fundusze aktywne — 10 lat danych",                 views=34200,  likes=1840, comments=263, revenue=102.60, pub_days_ago=21, dur=865),
    dict(idx=8, ch="ch_fit",     script=8, yt_id="plan12tygodni",  title="12-tygodniowy plan treningowy dla początkujących",        views=21000,  likes=980,  comments=147, revenue=0.0,    pub_days_ago=28, dur=912),
    dict(idx=9, ch="ch_fit",     script=9, yt_id="IF_nauka2025",   title="Post przerywany IF — co mówi nauka po 10 latach badań",   views=18500,  likes=820,  comments=134, revenue=0.0,    pub_days_ago=14, dur=803),
    # scheduled
    dict(idx=3, ch="ch_tech",    script=3, yt_id=None, title="Twój pierwszy agent AI z LangChain — tutorial",        views=0, likes=0, comments=0, revenue=0.0, pub_days_ago=None, dur=1180),
    dict(idx=6, ch="ch_finance", script=6, yt_id=None, title="Podatek Belki 2025 — 5 legalnych sposobów na zmniejszenie podatku", views=0, likes=0, comments=0, revenue=0.0, pub_days_ago=None, dur=754),
    # draft
    dict(idx=7, ch="ch_finance", script=7, yt_id=None, title="FIRE movement w Polsce — czy wolność finansowa jest możliwa?", views=0, likes=0, comments=0, revenue=0.0, pub_days_ago=None, dur=810),
    dict(idx=10, ch="ch_fit",    script=10, yt_id=None, title="30-minutowy trening w domu bez sprzętu — 8-tygodniowy program", views=0, likes=0, comments=0, revenue=0.0, pub_days_ago=None, dur=723),
]

_PUB_STATUS = {
    1: PublicationStatus.published, 2: PublicationStatus.published,
    4: PublicationStatus.published, 5: PublicationStatus.published,
    8: PublicationStatus.published, 9: PublicationStatus.published,
    3: PublicationStatus.scheduled, 6: PublicationStatus.scheduled,
    7: PublicationStatus.draft,    10: PublicationStatus.draft,
}
_PUB_VIS = {
    1: PublicationVisibility.public, 2: PublicationVisibility.public,
    4: PublicationVisibility.public, 5: PublicationVisibility.public,
    8: PublicationVisibility.public, 9: PublicationVisibility.public,
    3: PublicationVisibility.private, 6: PublicationVisibility.private,
    7: PublicationVisibility.private, 10: PublicationVisibility.private,
}


async def seed_publications(db) -> None:
    for p in _PUBLICATIONS:
        i = p["idx"]
        pub_at = dt(p["pub_days_ago"]) if p["pub_days_ago"] else None
        sched_at = dt(-(7)) if _PUB_STATUS[i] == PublicationStatus.scheduled else None
        db.add(Publication(
            id=UID[f"pub_{i}"],
            channel_id=_CH_MAP[p["ch"]],
            script_id=UID[f"script_{p['script']}"],
            youtube_video_id=p["yt_id"],
            title=p["title"],
            tags=_SCRIPTS[p["script"] - 1]["keywords"],
            status=_PUB_STATUS[i],
            visibility=_PUB_VIS[i],
            duration_seconds=p["dur"],
            published_at=pub_at,
            scheduled_at=sched_at,
            view_count=p["views"],
            like_count=p["likes"],
            comment_count=p["comments"],
            revenue_usd=p["revenue"],
        ))
    await db.flush()
    log.info("seed.publications.done", count=len(_PUBLICATIONS))


# ── Analytics ──────────────────────────────────────────────────────────────────

_PUBLISHED_PUBS = [1, 2, 4, 5, 8, 9]  # pub indices with status=published


async def seed_analytics(db) -> None:
    # Channel-level snapshots: 30 days per channel
    ch_configs = [
        ("ch_tech",    dict(base_views=1800, base_impr=28000, base_subs=12, ctr=0.065, rpm=3.8)),
        ("ch_finance", dict(base_views=1200, base_impr=18000, base_subs=8,  ctr=0.072, rpm=4.2)),
        ("ch_fit",     dict(base_views=600,  base_impr=10000, base_subs=5,  ctr=0.058, rpm=0.0)),
    ]
    for ch_key, cfg in ch_configs:
        for day in range(29, -1, -1):
            growth = 1.0 + (29 - day) * 0.008  # slight upward trend
            jitter = 0.85 + random.random() * 0.30
            views = int(cfg["base_views"] * growth * jitter)
            impr  = int(cfg["base_impr"]  * growth * jitter)
            wh    = round(views * 7.2 / 3600, 2)  # ~7.2 min avg * views
            rev   = round(wh * cfg["rpm"] / 1000, 4)
            db.add(AnalyticsSnapshot(
                channel_id=_CH_MAP[ch_key],
                publication_id=None,
                snapshot_date=d(day),
                snapshot_type=SnapshotType.channel,
                impressions=impr,
                views=views,
                ctr=cfg["ctr"] + random.uniform(-0.01, 0.01),
                watch_time_hours=wh,
                avg_view_duration_seconds=432 + random.randint(-60, 90),
                like_count=int(views * 0.048),
                comment_count=int(views * 0.007),
                subscribers_gained=int(cfg["base_subs"] * growth * jitter),
                subscribers_lost=random.randint(1, 3),
                revenue_usd=rev,
                rpm=cfg["rpm"] + random.uniform(-0.3, 0.3),
                cpm=cfg["rpm"] * 1.4 + random.uniform(-0.2, 0.2),
            ))

    # Publication-level snapshots: 14 days for each published publication
    pub_cfgs = {
        1: dict(ch="ch_tech",    daily_views=1100, ctr=0.072, rpm=3.9),
        2: dict(ch="ch_tech",    daily_views=2100, ctr=0.081, rpm=3.7),
        4: dict(ch="ch_finance", daily_views=1500, ctr=0.091, rpm=4.4),
        5: dict(ch="ch_finance", daily_views=1700, ctr=0.075, rpm=4.1),
        8: dict(ch="ch_fit",     daily_views=800,  ctr=0.062, rpm=0.0),
        9: dict(ch="ch_fit",     daily_views=1400, ctr=0.068, rpm=0.0),
    }
    for pub_idx, pcfg in pub_cfgs.items():
        for day in range(13, -1, -1):
            decay = max(0.3, 1.0 - day * 0.05)  # older days get less traffic
            jitter = 0.8 + random.random() * 0.4
            views = int(pcfg["daily_views"] * decay * jitter)
            wh = round(views * 6.5 / 3600, 2)
            rev = round(wh * pcfg["rpm"] / 1000, 4)
            db.add(AnalyticsSnapshot(
                channel_id=_CH_MAP[pcfg["ch"]],
                publication_id=UID[f"pub_{pub_idx}"],
                snapshot_date=d(day),
                snapshot_type=SnapshotType.publication,
                impressions=int(views * 14),
                views=views,
                ctr=pcfg["ctr"] + random.uniform(-0.01, 0.01),
                watch_time_hours=wh,
                avg_view_duration_seconds=400 + random.randint(-40, 80),
                like_count=int(views * 0.045),
                comment_count=int(views * 0.006),
                subscribers_gained=random.randint(1, 8),
                subscribers_lost=0,
                revenue_usd=rev,
                rpm=pcfg["rpm"],
                cpm=pcfg["rpm"] * 1.35,
            ))

    await db.flush()
    log.info("seed.analytics.done")


# ── Performance scores ─────────────────────────────────────────────────────────

async def seed_performance_scores(db) -> None:
    ch_scores = [
        ("ch_tech",    dict(score=72.4, view=68, ctr=74, ret=71, rev=78, grow=70, views=52400, ctr_r=0.067, ret_r=0.43, rpm=3.8, rev_r=198.4, subs=320)),
        ("ch_finance", dict(score=68.1, view=62, ctr=79, ret=66, rev=71, grow=63, views=34200, ctr_r=0.073, ret_r=0.41, rpm=4.2, rev_r=143.5, subs=210)),
        ("ch_fit",     dict(score=55.8, view=51, ctr=58, ret=62, rev=20, grow=68, views=19200, ctr_r=0.059, ret_r=0.38, rpm=0.0, rev_r=0.0,   subs=140)),
    ]
    for ch_key, s in ch_scores:
        for period in [7, 30, 90]:
            mult = {7: 0.25, 30: 1.0, 90: 3.2}[period]
            db.add(PerformanceScore(
                channel_id=_CH_MAP[ch_key],
                publication_id=None,
                period_days=period,
                score=s["score"],
                view_score=s["view"],
                ctr_score=s["ctr"],
                retention_score=s["ret"],
                revenue_score=s["rev"],
                growth_score=s["grow"],
                raw_views=int(s["views"] * mult),
                raw_ctr=s["ctr_r"],
                raw_retention=s["ret_r"],
                raw_rpm=s["rpm"],
                raw_revenue=round(s["rev_r"] * mult, 2),
                raw_subs_net=int(s["subs"] * mult),
                computed_at=NOW,
            ))

    # Per-publication scores (30-day)
    pub_scores = [
        (1, "ch_tech",    dict(score=78.2, view=74, ctr=81, ret=76, rev=80, grow=79, views=45200, ctr_r=0.072, ret_r=0.46, rpm=3.9, rev_r=135.4, subs=89,  rank_ch=1, rank_all=12)),
        (2, "ch_tech",    dict(score=84.1, view=89, ctr=85, ret=81, rev=82, grow=83, views=62100, ctr_r=0.081, ret_r=0.49, rpm=3.7, rev_r=186.3, subs=124, rank_ch=2, rank_all=7)),
        (4, "ch_finance", dict(score=91.3, view=94, ctr=92, ret=88, rev=91, grow=91, views=89400, ctr_r=0.091, ret_r=0.52, rpm=4.4, rev_r=267.9, subs=198, rank_ch=1, rank_all=3)),
        (5, "ch_finance", dict(score=72.4, view=68, ctr=76, ret=71, rev=74, grow=73, views=34200, ctr_r=0.075, ret_r=0.44, rpm=4.1, rev_r=102.6, subs=87,  rank_ch=2, rank_all=18)),
        (8, "ch_fit",     dict(score=63.2, view=61, ctr=65, ret=67, rev=10, grow=72, views=21000, ctr_r=0.062, ret_r=0.41, rpm=0.0, rev_r=0.0,   subs=76,  rank_ch=1, rank_all=31)),
        (9, "ch_fit",     dict(score=58.7, view=55, ctr=62, ret=63, rev=10, grow=64, views=18500, ctr_r=0.068, ret_r=0.39, rpm=0.0, rev_r=0.0,   subs=62,  rank_ch=2, rank_all=38)),
    ]
    for pub_idx, ch_key, s in pub_scores:
        db.add(PerformanceScore(
            channel_id=_CH_MAP[ch_key],
            publication_id=UID[f"pub_{pub_idx}"],
            period_days=30,
            score=s["score"],
            view_score=s["view"],
            ctr_score=s["ctr"],
            retention_score=s["ret"],
            revenue_score=s["rev"],
            growth_score=s["grow"],
            raw_views=s["views"],
            raw_ctr=s["ctr_r"],
            raw_retention=s["ret_r"],
            raw_rpm=s["rpm"],
            raw_revenue=s["rev_r"],
            raw_subs_net=s["subs"],
            rank_in_channel=s["rank_ch"],
            rank_overall=s["rank_all"],
            computed_at=NOW,
        ))

    await db.flush()
    log.info("seed.performance.done")


# ── Recommendations ────────────────────────────────────────────────────────────

async def seed_recommendations(db) -> None:
    recs = [
        Recommendation(channel_id=_CH_MAP["ch_tech"], publication_id=UID["pub_1"],
            rec_type=RecommendationType.improve_thumbnail, priority=RecommendationPriority.high,
            status=RecommendationStatus.pending, source=RecommendationSource.ai,
            title="Zmień miniaturę — CTR poniżej średniej kanału",
            body="Miniatura publikacji #1 generuje CTR 6.5% przy średniej kanału 7.8%. Twarze w miniaturze zwiększają CTR o 38% według badań YouTube.",
            rationale="CTR jest głównym sygnałem rankingowym. Wzrost z 6.5% do 7.5% = +15% wyświetleń organicznych.",
            metric_key="ctr", metric_current=0.065, metric_target=0.078, impact_label="+15% wyświetleń"),
        Recommendation(channel_id=_CH_MAP["ch_tech"], publication_id=UID["pub_2"],
            rec_type=RecommendationType.scale_topic, priority=RecommendationPriority.high,
            status=RecommendationStatus.pending, source=RecommendationSource.ai,
            title="Skaluj format — porównania AI performują 2.3x lepiej",
            body="Wideo z porównaniem modeli AI (pub #2) osiągnęło 62K wyświetleń — 2.3x więcej niż średnia kanału. Zrób serię: Claude vs Gemini, GPT-4o vs Llama, lokalne vs chmurowe.",
            rationale="Replikowanie sprawdzonego formatu przy niskim koszcie produkcji.",
            metric_key="views", metric_current=62100.0, metric_target=120000.0, impact_label="Seria 5 odcinków"),
        Recommendation(channel_id=_CH_MAP["ch_tech"], topic_id=UID["topic_7"],
            rec_type=RecommendationType.kill_topic, priority=RecommendationPriority.medium,
            status=RecommendationStatus.dismissed, source=RecommendationSource.rule,
            title="Porzuć temat quantum computing",
            body="Temat 'Quantum computing dla laika' ma trend_score 6.3 — najniższy w kanale. Wyszukiwalność frazy w Polsce jest 12x niższa niż tematy AI/LLM.",
            rationale="Ograniczone zasoby powinny trafiać do tematów z najwyższym potencjałem.",
            metric_key="trend_score", metric_current=6.3, metric_target=0.0, impact_label="Uwolnienie zasobów"),
        Recommendation(channel_id=_CH_MAP["ch_finance"], publication_id=UID["pub_4"],
            rec_type=RecommendationType.repeat_format, priority=RecommendationPriority.critical,
            status=RecommendationStatus.pending, source=RecommendationSource.ai,
            title="Replikuj format 'kompletny przewodnik' — najlepszy wynik kanału",
            body="'Inwestowanie 500 zł' (89K wyświetleń) to najlepiej performujące wideo w historii kanału. Format: konkretna kwota + 'kompletny przewodnik' + persone początkującego.",
            rationale="Sprawdzony format = niższe ryzyko, wyższy ROI produkcji.",
            metric_key="views", metric_current=89400.0, metric_target=150000.0, impact_label="Seria 4 odcinków"),
        Recommendation(channel_id=_CH_MAP["ch_finance"], publication_id=UID["pub_5"],
            rec_type=RecommendationType.improve_hook, priority=RecommendationPriority.medium,
            status=RecommendationStatus.applied, source=RecommendationSource.ai,
            title="Przepisz hook — retencja w pierwszych 30s poniżej progu",
            body="Retencja w pierwszych 30 sekundach to 52% przy benchmarku 65% dla filmów finansowych. Hook nie zadaje pytania, które zatrzymuje widza.",
            rationale="Wzrost retencji 30s z 52% do 62% = +20% średniego czasu oglądania.",
            metric_key="retention_30s", metric_current=0.52, metric_target=0.65, impact_label="+20% watch time"),
        Recommendation(channel_id=_CH_MAP["ch_fit"], topic_id=UID["topic_20"],
            rec_type=RecommendationType.scale_topic, priority=RecommendationPriority.high,
            status=RecommendationStatus.pending, source=RecommendationSource.rule,
            title="Skaluj treningi domowe — trend_score najwyższy w kanale",
            body="Temat 'Trening w domu' ma trend_score 9.0 — najwyższy ze wszystkich tematów FitLife. Wyszukiwalność +34% rok do roku.",
            rationale="Rosnący trend + sprawdzona nisza kanału = optymalny kierunek rozwoju.",
            metric_key="trend_score", metric_current=9.0, metric_target=9.0, impact_label="Seria sezonowa"),
        Recommendation(channel_id=_CH_MAP["ch_fit"],
            rec_type=RecommendationType.localize, priority=RecommendationPriority.low,
            status=RecommendationStatus.snoozed, source=RecommendationSource.rule,
            title="Rozważ angielskie napisy — 23% ruchu spoza Polski",
            body="Analytics pokazuje 23% wyświetleń z krajów anglojęzycznych (UK, IE, US). Angielskie napisy mogą zwiększyć zasięg bez dodatkowej produkcji.",
            rationale="Niski koszt implementacji (napisy auto + korekta) przy potencjalnie dużym zasięgu.",
            metric_key=None, metric_current=0.23, metric_target=0.35, impact_label="+12% zasięg"),
    ]
    for rec in recs:
        db.add(rec)
    await db.flush()
    log.info("seed.recommendations.done", count=len(recs))


# ── Revenue & Affiliate ────────────────────────────────────────────────────────

async def seed_revenue(db) -> None:
    # Published publication ad revenue
    pub_rev = [
        (1, "ch_tech",    45, 135.40),
        (2, "ch_tech",    30, 186.30),
        (4, "ch_finance", 60, 267.90),
        (5, "ch_finance", 21, 102.60),
    ]
    for pub_idx, ch_key, days, rev in pub_rev:
        db.add(RevenueStream(
            channel_id=_CH_MAP[ch_key],
            publication_id=UID[f"pub_{pub_idx}"],
            source=RevenueSource.ads,
            period_start=d(days),
            period_end=TODAY,
            revenue_usd=rev,
            impressions=int(rev / 3.8 * 1000),
            clicks=0,
            conversions=0,
            rpm=3.8,
            cpm=5.1,
            cost_usd=0.0,
            roi_pct=None,
            is_estimated=False,
        ))

    # Monthly channel-level affiliate aggregate
    channel_affiliate = [
        ("ch_tech",    348.50),
        ("ch_finance", 212.80),
    ]
    for ch_key, rev in channel_affiliate:
        db.add(RevenueStream(
            channel_id=_CH_MAP[ch_key],
            publication_id=None,
            source=RevenueSource.affiliate,
            period_start=d(30),
            period_end=TODAY,
            revenue_usd=rev,
            impressions=0,
            clicks=int(rev / 12.5 * 5),
            conversions=int(rev / 12.5),
            rpm=0.0,
            cpm=0.0,
            commission_rate=0.08,
            cost_usd=0.0,
            roi_pct=None,
            is_estimated=True,
        ))

    await db.flush()

    # Affiliate links
    links = [
        AffiliateLink(channel_id=_CH_MAP["ch_tech"], platform=AffiliatePlatform.amazon,
            name="Książki o AI — Amazon PL", destination_url="https://amazon.pl/dp/B0EXAMPLE1",
            slug="tech-ai-books", tracking_id="techinsider-21", commission_type="percentage",
            commission_value=4.0, total_clicks=1240, total_conversions=87, total_revenue_usd=218.50, is_active=True),
        AffiliateLink(channel_id=_CH_MAP["ch_tech"], platform=AffiliatePlatform.custom,
            name="Cursor IDE — 20% zniżka", destination_url="https://cursor.sh/ref/techinsider",
            slug="tech-cursor", tracking_id="TI2024", commission_type="fixed",
            commission_value=15.0, total_clicks=340, total_conversions=23, total_revenue_usd=345.0, is_active=True),
        AffiliateLink(channel_id=_CH_MAP["ch_finance"], platform=AffiliatePlatform.custom,
            name="XTB — otwarcie konta maklerskiego", destination_url="https://xtb.com/pl/partner/finanse",
            slug="fin-xtb", tracking_id="FP2024XTB", commission_type="fixed",
            commission_value=100.0, total_clicks=892, total_conversions=34, total_revenue_usd=3400.0, is_active=True),
        AffiliateLink(channel_id=_CH_MAP["ch_finance"], platform=AffiliatePlatform.amazon,
            name="Książki o inwestowaniu", destination_url="https://amazon.pl/dp/B0EXAMPLE2",
            slug="fin-books", tracking_id="finansep-21", commission_type="percentage",
            commission_value=4.0, total_clicks=456, total_conversions=31, total_revenue_usd=77.50, is_active=True),
        AffiliateLink(channel_id=_CH_MAP["ch_fit"], platform=AffiliatePlatform.custom,
            name="MyProtein — suplementy 30% taniej", destination_url="https://myprotein.pl/ref/fitlife",
            slug="fit-protein", tracking_id="FLD2024MP", commission_type="percentage",
            commission_value=8.0, total_clicks=678, total_conversions=52, total_revenue_usd=187.20, is_active=True),
    ]
    for link in links:
        db.add(link)
    await db.flush()
    log.info("seed.revenue.done")


# ── Compliance ─────────────────────────────────────────────────────────────────

async def seed_compliance(db) -> None:
    all_cats = ["ad_safety", "copyright_risk", "factual_risk", "reused_content", "ai_disclosure"]
    zero_scores = {c: 0.0 for c in all_cats}

    # 7 passed checks (scripts 1,2,4,5,6,8,9)
    for script_idx in [1, 2, 4, 5, 6, 8, 9]:
        ch_key = next(s["ch"] for s in _SCRIPTS if s["idx"] == script_idx)
        db.add(ComplianceCheck(
            id=UID[f"check_{script_idx}"],
            channel_id=_CH_MAP[ch_key],
            script_id=UID[f"script_{script_idx}"],
            mode=CheckMode.both,
            status=CheckStatus.passed,
            risk_score=random.uniform(4.0, 18.0),
            category_scores=zero_scores.copy(),
            flag_count=0, critical_count=0, high_count=0,
            monetization_eligible=True,
            ai_disclosure_required=False,
            started_at=dt(2), completed_at=dt(2, hour=13),
            ai_task_ids={},
        ))

    # Flagged check — script 3 (LangChain tutorial)
    flagged_scores = {"ad_safety": 0.0, "copyright_risk": 40.0, "factual_risk": 40.0, "reused_content": 0.0, "ai_disclosure": 0.0}
    flagged_risk = 40.0 * 0.30 + 40.0 * 0.20  # 12 + 8 = 20 → actually need > 21
    flagged_risk = 24.5 + 8.0  # high copyright (70*0.30=21) + medium factual (40*0.20=8) = 29
    flagged_scores = {"ad_safety": 0.0, "copyright_risk": 70.0, "factual_risk": 40.0, "reused_content": 0.0, "ai_disclosure": 0.0}
    flagged_risk = round(70.0 * 0.30 + 40.0 * 0.20, 2)  # 21.0 + 8.0 = 29.0

    check3 = ComplianceCheck(
        id=UID["check_3"],
        channel_id=_CH_MAP["ch_tech"],
        script_id=UID["script_3"],
        mode=CheckMode.both,
        status=CheckStatus.flagged,
        risk_score=flagged_risk,
        category_scores=flagged_scores,
        flag_count=2, critical_count=0, high_count=1,
        monetization_eligible=True,
        ai_disclosure_required=False,
        started_at=dt(1), completed_at=dt(1, hour=13),
        ai_task_ids={"copyright_risk": "task_abc123", "factual_risk": "task_def456"},
    )
    db.add(check3)
    await db.flush()

    db.add(RiskFlag(
        check_id=UID["check_3"],
        category=RiskCategory.copyright_risk,
        severity=RiskSeverity.high,
        source=FlagSource.ai,
        rule_id="copyright_risk:code:c001",
        title="Potencjalne naruszenie licencji kodu",
        detail="Fragment kodu w sekcji 'implementacja agenta' może być objęty licencją Apache 2.0 wymagającą atrybucji.",
        evidence="from langchain.agents import AgentExecutor, create_react_agent",
        suggestion="Dodaj atrybucję LangChain/Harrison Chase w opisie wideo lub komentarzu do kodu.",
    ))
    db.add(RiskFlag(
        check_id=UID["check_3"],
        category=RiskCategory.factual_risk,
        severity=RiskSeverity.medium,
        source=FlagSource.rule,
        rule_id="factual_risk:claims:f003",
        title="Niesprecyzowane twierdzenie o skuteczności",
        detail="Wyrażenie 'agent wykona zadanie autonomicznie' jest zbyt absolutne — LLM agents mają ograniczenia.",
        evidence="agent wykona zadanie autonomicznie",
        suggestion="Zmień na 'agent spróbuje wykonać zadanie, wymagając weryfikacji dla złożonych przypadków'.",
    ))

    # Flagged+overridden check — script 7 (FIRE movement)
    blocked_scores = {"ad_safety": 0.0, "copyright_risk": 0.0, "factual_risk": 70.0, "reused_content": 0.0, "ai_disclosure": 0.0}
    blocked_risk = round(70.0 * 0.20, 2)  # 14 — actually not blocked enough
    # Make it actually flagged-but-overridden:
    blocked_scores = {"ad_safety": 0.0, "copyright_risk": 40.0, "factual_risk": 70.0, "reused_content": 40.0, "ai_disclosure": 0.0}
    blocked_risk = round(40.0 * 0.30 + 70.0 * 0.20 + 40.0 * 0.10, 2)  # 12+14+4 = 30

    check7 = ComplianceCheck(
        id=UID["check_7"],
        channel_id=_CH_MAP["ch_finance"],
        script_id=UID["script_7"],
        mode=CheckMode.both,
        status=CheckStatus.flagged,
        risk_score=blocked_risk,
        category_scores=blocked_scores,
        flag_count=3, critical_count=0, high_count=1,
        monetization_eligible=True,
        ai_disclosure_required=False,
        is_overridden=True,
        override_by="Admin",
        override_reason="Skrypt zawiera standardowe ostrzeżenia FIRE movement. Twierdzenia zweryfikowane przez prawnika — nie stanowią porady finansowej w sensie MiFID II.",
        overridden_at=dt(0, hour=10),
        started_at=dt(1), completed_at=dt(1, hour=14),
        ai_task_ids={},
    )
    db.add(check7)
    await db.flush()

    db.add(RiskFlag(
        check_id=UID["check_7"],
        category=RiskCategory.factual_risk,
        severity=RiskSeverity.high,
        source=FlagSource.ai,
        rule_id="factual_risk:financial:f002",
        title="Niezweryfikowana projekcja finansowa",
        detail="Twierdzenie 'Przy 500 zł miesięcznie i 8% zysku rocznie będziesz mieć 745 000 zł' to projekcja wymagająca zastrzeżenia.",
        evidence="będziesz mieć 745 000 złotych",
        suggestion="Dodaj zastrzeżenie: 'wyniki historyczne nie gwarantują przyszłych zwrotów'.",
    ))
    db.add(RiskFlag(
        check_id=UID["check_7"],
        category=RiskCategory.copyright_risk,
        severity=RiskSeverity.medium,
        source=FlagSource.rule,
        rule_id="copyright_risk:strategy:c003",
        title="Odwołanie do strategii FIRE bez atrybucji",
        detail="FIRE movement jest koncepcją publiczną, ale konkretne liczby mogą pochodzić ze źródeł wymagających cytowania.",
        evidence="Reguła 4%",
        suggestion="Zacytuj badanie Bengen 1994 lub Trinity Study jako źródło reguły 4%.",
    ))
    db.add(RiskFlag(
        check_id=UID["check_7"],
        category=RiskCategory.reused_content,
        severity=RiskSeverity.medium,
        source=FlagSource.rule,
        rule_id="reused_content:similarity:r001",
        title="Podobny tytuł w istniejących materiałach",
        detail="Tytuł jest zbliżony (similarity 0.81) do poprzedniego odcinka o niezależności finansowej.",
        evidence="FIRE movement w Polsce",
        suggestion="Zmień tytuł na bardziej unikalny, np. 'Emerytura w 40 lat — mój plan FIRE na polskim rynku'.",
    ))

    # Running check — script 10
    db.add(ComplianceCheck(
        id=UID["check_10"],
        channel_id=_CH_MAP["ch_fit"],
        script_id=UID["script_10"],
        mode=CheckMode.both,
        status=CheckStatus.running,
        risk_score=0.0,
        category_scores=zero_scores.copy(),
        flag_count=0, critical_count=0, high_count=0,
        monetization_eligible=True,
        ai_disclosure_required=False,
        started_at=NOW,
        ai_task_ids={"ad_safety": "task_run001", "copyright_risk": "task_run002", "factual_risk": "task_run003"},
    ))

    await db.flush()
    log.info("seed.compliance.done")


# ── Pipelines & Workflows ──────────────────────────────────────────────────────

_PIPELINE_STEPS_FULL = [
    {"id": "topic_research", "type": "ai_task", "name": "Badanie tematu", "timeout": 120},
    {"id": "brief_generation", "type": "ai_task", "name": "Generowanie briefu", "timeout": 180},
    {"id": "script_writing", "type": "ai_task", "name": "Pisanie skryptu", "timeout": 300},
    {"id": "compliance_check", "type": "compliance", "name": "Sprawdzenie zgodności", "timeout": 90},
    {"id": "publication", "type": "manual", "name": "Publikacja wideo", "timeout": None},
]
_PIPELINE_STEPS_QUICK = [
    {"id": "brief_generation", "type": "ai_task", "name": "Generowanie briefu", "timeout": 180},
    {"id": "script_writing", "type": "ai_task", "name": "Pisanie skryptu", "timeout": 300},
    {"id": "compliance_check", "type": "compliance", "name": "Sprawdzenie zgodności", "timeout": 90},
]


async def seed_pipelines_and_workflows(db) -> None:
    pipe_full = Pipeline(
        id=UID["pipe_full"],
        owner_id=UID["user"],
        channel_id=UID["ch_tech"],
        name="Pełny Pipeline Treści",
        description="Od tematu do publikacji — 5 kroków z weryfikacją zgodności.",
        steps=_PIPELINE_STEPS_FULL,
        is_active=True,
        schedule_cron=None,
    )
    pipe_quick = Pipeline(
        id=UID["pipe_quick"],
        owner_id=UID["user"],
        channel_id=None,
        name="Szybki Pipeline Skryptu",
        description="Brief → Skrypt → Compliance. Bez publikacji, dla szybkich iteracji.",
        steps=_PIPELINE_STEPS_QUICK,
        is_active=True,
        schedule_cron="0 9 * * 1",  # Monday 9:00
    )
    db.add(pipe_full)
    db.add(pipe_quick)
    await db.flush()

    # Pipeline run 1 — completed
    run1 = PipelineRun(
        pipeline_id=UID["pipe_full"],
        status=PipelineRunStatus.completed,
        triggered_by="manual",
        input={"channel_id": str(UID["ch_tech"]), "topic": "Claude vs GPT-4o"},
        output={"script_id": str(UID["script_2"]), "compliance": "passed"},
        step_results=[
            {"step_id": s["id"], "status": "completed", "duration_ms": random.randint(800, 4200)}
            for s in _PIPELINE_STEPS_FULL
        ],
        started_at=str(dt(30)),
        completed_at=str(dt(30, hour=14)),
    )
    db.add(run1)
    await db.flush()
    for step in _PIPELINE_STEPS_FULL:
        db.add(PipelineStepResult(
            run_id=run1.id, step_id=step["id"],
            status=PipelineRunStatus.completed,
            output={"result": f"step_{step['id']}_done"},
            retry_count=0,
        ))

    # Pipeline run 2 — failed
    run2 = PipelineRun(
        pipeline_id=UID["pipe_quick"],
        status=PipelineRunStatus.failed,
        triggered_by="schedule",
        input={"channel_id": str(UID["ch_finance"]), "topic": "ETF ranking 2025"},
        output=None,
        error="LLM API timeout during script_writing step after 300s",
        step_results=[
            {"step_id": "brief_generation", "status": "completed", "duration_ms": 2100},
            {"step_id": "script_writing", "status": "failed", "duration_ms": 300000, "error": "timeout"},
            {"step_id": "compliance_check", "status": "cancelled", "duration_ms": 0},
        ],
        started_at=str(dt(14)),
        completed_at=str(dt(14, hour=10)),
    )
    db.add(run2)
    await db.flush()
    for sid, status_val in [("brief_generation", PipelineRunStatus.completed), ("script_writing", PipelineRunStatus.failed), ("compliance_check", PipelineRunStatus.cancelled)]:
        db.add(PipelineStepResult(run_id=run2.id, step_id=sid, status=status_val, retry_count=1 if status_val == PipelineRunStatus.failed else 0))

    await db.flush()

    # Workflow runs
    wf_runs = [
        (UID["run_tech1"], "ch_tech",    RunStatus.completed, "Pełny Pipeline Treści", dt(30), dt(30, hour=14)),
        (UID["run_fin1"],  "ch_finance", RunStatus.completed, "Pełny Pipeline Treści", dt(21), dt(21, hour=15)),
        (UID["run_fit1"],  "ch_fit",     RunStatus.running,   "Pełny Pipeline Treści", NOW,    None),
        (UID["run_tech2"], "ch_tech",    RunStatus.failed,    "Szybki Pipeline Skryptu", dt(14), dt(14, hour=10)),
    ]
    for run_id, ch_key, status, pipe_name, started, completed in wf_runs:
        wr = WorkflowRun(
            id=run_id,
            channel_id=_CH_MAP[ch_key],
            owner_id=UID["user"],
            pipeline_name=pipe_name,
            pipeline_version="1.0",
            status=status,
            triggered_by="manual" if status != RunStatus.running else "schedule",
            context={"channel_id": str(_CH_MAP[ch_key])},
            error="LLM timeout podczas generowania skryptu" if status == RunStatus.failed else None,
            started_at=started,
            completed_at=completed,
        )
        db.add(wr)
        await db.flush()

        # Jobs
        steps = _PIPELINE_STEPS_FULL if "Pełny" in pipe_name else _PIPELINE_STEPS_QUICK
        for j, step in enumerate(steps):
            if status == RunStatus.completed:
                job_status = JobStatus.completed
                jstart, jend = started + timedelta(minutes=j * 8), started + timedelta(minutes=j * 8 + 6)
                dur = random.randint(1200, 8500)
            elif status == RunStatus.failed and j >= 2:
                job_status = JobStatus.failed if j == 2 else JobStatus.cancelled
                jstart = started + timedelta(minutes=j * 8) if j == 2 else None
                jend = None
                dur = None
            elif status == RunStatus.running:
                job_status = JobStatus.completed if j == 0 else (JobStatus.running if j == 1 else JobStatus.pending)
                jstart = started if j <= 1 else None
                jend = started + timedelta(minutes=6) if j == 0 else None
                dur = random.randint(1200, 3000) if j == 0 else None
            else:
                job_status = JobStatus.completed
                jstart, jend, dur = started, completed, 3000

            db.add(WorkflowJob(
                run_id=run_id,
                step_id=step["id"],
                step_type=step["type"],
                status=job_status,
                attempt=1,
                max_attempts=3,
                input={"step": step["id"]},
                output={"done": True} if job_status == JobStatus.completed else None,
                error="timeout" if job_status == JobStatus.failed else None,
                started_at=jstart,
                completed_at=jend,
                duration_ms=dur,
            ))

        # Audit events
        events = [("run_started", "system", {"pipeline": pipe_name})]
        if status in (RunStatus.completed, RunStatus.failed):
            events.append(("job_completed", "system", {"step": steps[0]["id"]}))
        if status == RunStatus.failed:
            events.append(("job_failed", "system", {"step": steps[2]["id"], "error": "timeout"}))
            events.append(("run_failed", "system", {"reason": "step_failure"}))
        elif status == RunStatus.completed:
            events.append(("run_completed", "system", {"duration_s": 480}))
        for ev_type, actor, data in events:
            db.add(WorkflowAuditEvent(run_id=run_id, event_type=ev_type, actor=actor, data=data, occurred_at=started or NOW))

    await db.flush()
    log.info("seed.workflows.done")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("seed.start")
    async with AsyncSessionLocal() as db:
        # Idempotent: cascade from user clears all related seed data
        await db.execute(delete(User).where(User.email == "demo@aimediaos.com"))
        await db.commit()

        await seed_user(db)
        await seed_channels(db)
        await seed_topics(db)
        await seed_briefs(db)
        await seed_scripts(db)
        await seed_publications(db)
        await seed_analytics(db)
        await seed_performance_scores(db)
        await seed_recommendations(db)
        await seed_revenue(db)
        await seed_compliance(db)
        await seed_pipelines_and_workflows(db)

        await db.commit()

    print("\n✓ Seed complete.")
    print("  Login:    demo@aimediaos.com")
    print("  Password: demo1234")
    print("  Channels: TechInsider PL · Finanse Praktyczne · FitLife Daily")
    log.info("seed.complete")


if __name__ == "__main__":
    asyncio.run(main())
