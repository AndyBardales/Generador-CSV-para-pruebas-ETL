from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from faker import Faker
except ImportError:
    print("ERROR: No está instalada Faker. Ejecuta: py -m pip install -r requirements.txt")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
CATALOG_DIR = BASE_DIR / "catalogos"

ORIGINAL_COLUMNS = {
    "customers": [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state",
    ],
    "sellers": [
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state",
    ],
    "products": [
        "product_id", "product_category_name", "product_name_lenght",
        "product_description_lenght", "product_photos_qty", "product_weight_g",
        "product_length_cm", "product_height_cm", "product_width_cm",
    ],
    "geolocation": [
        "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
        "geolocation_city", "geolocation_state",
    ],
    "translation": ["product_category_name", "product_category_name_english"],
    "orders": [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "items": ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
    "payments": ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    "reviews": [
        "review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
        "review_creation_date", "review_answer_timestamp",
    ],
}


def read_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No se encontró {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["N_ORDERS", "N_PRODUCTS", "N_SELLERS", "N_GEOLOCATIONS", "SEED", "OUTPUT_DIR"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Falta la clave {key} en config.json")
    for key in ["N_ORDERS", "N_PRODUCTS", "N_SELLERS", "N_GEOLOCATIONS"]:
        if int(cfg[key]) < 1:
            raise ValueError(f"{key} debe ser mayor que cero")
    rate = float(cfg.get("REPEAT_CUSTOMER_RATE", 0.05))
    if not 0 <= rate < 1:
        raise ValueError("REPEAT_CUSTOMER_RATE debe estar entre 0 y menor que 1")
    return cfg


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el catálogo: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [{str(k).strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def random_date(rng: random.Random, start: date, end: date) -> str:
    if end < start:
        start, end = end, start
    days = (end - start).days
    return (start + timedelta(days=rng.randint(0, max(0, days)))).isoformat()


def weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    values = [v for v, _ in choices]
    weights = [w for _, w in choices]
    return rng.choices(values, weights=weights, k=1)[0]


def load_catalogs() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    categories = read_csv_rows(CATALOG_DIR / "categorias.csv")
    brands = read_csv_rows(CATALOG_DIR / "marcas.csv")
    locations = read_csv_rows(CATALOG_DIR / "localizacoes_brasil.csv")
    if not categories or not brands or not locations:
        raise ValueError("Los catálogos no deben estar vacíos")
    for row in categories:
        for key in ["product_category_name", "product_category_name_english", "grupo", "nombres_base", "adjetivos"]:
            if not row.get(key):
                raise ValueError(f"Categoría incompleta: falta {key}: {row}")
    return categories, brands, locations


def generate_geolocation(
    n_rows: int,
    locations: list[dict[str, str]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Genera prefijos postales y coordenadas sintéticas aproximadas alrededor de ciudades de referencia."""
    rows: list[dict[str, Any]] = []
    used_prefixes: set[str] = set()
    counters = {loc["city"]: 0 for loc in locations}
    for i in range(n_rows):
        loc = locations[i % len(locations)]
        counters[loc["city"]] += 1
        base = int(loc["cep_prefix_base"])
        # El prefijo se deriva de una base sintética por localidad; se mantiene como texto de 5 dígitos.
        candidate = (base + counters[loc["city"]] - 1) % 100000
        prefix = f"{candidate:05d}"
        while prefix in used_prefixes:
            candidate = (candidate + 1) % 100000
            prefix = f"{candidate:05d}"
        used_prefixes.add(prefix)
        lat = float(loc["latitude"]) + rng.uniform(-0.035, 0.035)
        lng = float(loc["longitude"]) + rng.uniform(-0.035, 0.035)
        rows.append({
            "geolocation_zip_code_prefix": prefix,
            "geolocation_lat": f"{lat:.6f}",
            "geolocation_lng": f"{lng:.6f}",
            "geolocation_city": loc["city"],
            "geolocation_state": loc["state"],
        })
    return rows


def generate_customers(
    n_rows: int,
    repeat_rate: float,
    geolocations: list[dict[str, Any]],
    fake: Faker,
    rng: random.Random,
    date_start: date,
    date_end: date,
) -> list[dict[str, Any]]:
    """Olist usa un customer_id por registro asociado a un pedido; customer_unique_id representa a la persona."""
    n_unique = max(1, min(n_rows, round(n_rows * (1 - repeat_rate))))
    geo_by_prefix = {row["geolocation_zip_code_prefix"]: row for row in geolocations}
    profiles: list[dict[str, Any]] = []
    for i in range(1, n_unique + 1):
        geo = rng.choice(geolocations)
        profile_id = f"CUN{i:07d}"
        profiles.append({
            "customer_unique_id": profile_id,
            "customer_zip_code_prefix": geo["geolocation_zip_code_prefix"],
            "customer_city": geo["geolocation_city"],
            "customer_state": geo["geolocation_state"],
            "customer_name": fake.name(),
            "customer_email": f"cliente{i:07d}@example.com",
            # DDD 00 é intencionalmente inválido para evitar que o dado seja usado como contato real.
            "customer_phone": f"+55 (00) 90000-{i % 10000:04d}",
            "customer_since": random_date(rng, date(2015, 1, 1), date_start),
        })
    row_profiles = profiles.copy()
    while len(row_profiles) < n_rows:
        row_profiles.append(rng.choice(profiles))
    rng.shuffle(row_profiles)
    rows: list[dict[str, Any]] = []
    for i, profile in enumerate(row_profiles, start=1):
        row = {
            "customer_id": f"CUS{i:07d}",
            **profile,
        }
        rows.append(row)
    # Control adicional: todo prefixo de clientes debe existir en la tabla de geolocalización.
    missing = {r["customer_zip_code_prefix"] for r in rows} - set(geo_by_prefix)
    if missing:
        raise ValueError(f"Clientes con prefijos sin geolocalización: {sorted(missing)[:5]}")
    return rows


def build_seller_name(rng: random.Random, seller_type: str, index: int, used_names: set[str]) -> str:
    prefixes = ["Mundo", "Nova", "Ponto", "Central", "Ateliê", "Rede", "Grupo", "Viva", "Top", "Horizonte", "Estação", "Armazém", "Prático", "Prime", "Vale", "Brisa", "Nexo", "Estilo", "Conecta", "Casa"]
    suffixes = {
        "Loja de tecnologia": ["Digital", "Tecnologia", "Eletrônicos", "Tech", "Informática", "Conecta"],
        "Loja de casa e decoração": ["Decoração", "do Lar", "Ambientes", "Utilidades", "Design", "Lar & Cia"],
        "Loja de moda": ["Moda", "Urbana", "Vestuário", "Acessórios", "Tendências", "Estilo"],
        "Distribuidor": ["Distribuidora", "Atacado", "Suprimentos", "Comercial", "Logística", "Atacadista"],
        "Loja multicanal": ["Mix", "Ofertas", "Variedades", "Marketplace", "Center", "Utilidades"],
        "Fabricante": ["Indústria", "Fábrica", "Produtos", "Manufatura", "Produções", "Brasil"],
        "Loja automotiva": ["Auto Peças", "Motor", "Auto Center", "Acessórios Automotivos"],
        "Loja de beleza": ["Beleza", "Cosméticos", "Cuidados Pessoais", "Perfumaria"],
        "Loja pet": ["Pet Shop", "Mundo Pet", "Amigos dos Animais", "Pet Center"],
        "Livraria": ["Livraria", "Livros", "Leitura", "Papelaria e Livros"],
        "Loja de ferramentas": ["Ferramentas", "Casa do Profissional", "Suprimentos Técnicos", "Oficina"],
        "Loja de bebidas": ["Bebidas", "Adega", "Distribuidora de Bebidas", "Empório"],
        "Loja de esportes": ["Esportes", "Vida Ativa", "Artigos Esportivos", "Movimento"],
        "Loja infantil": ["Infantil", "Mundo da Criança", "Pequenos", "Bebê e Criança"],
    }
    options = suffixes.get(seller_type, ["Comércio", "Mix", "Center"])
    for _ in range(100):
        candidate = f"{rng.choice(prefixes)} {rng.choice(options)}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
    # Solo se agotan las combinaciones se agrega un consecutivo para garantizar unicidad.
    candidate = f"{rng.choice(prefixes)} {rng.choice(options)} {index:03d}"
    while candidate in used_names:
        candidate += "X"
    used_names.add(candidate)
    return candidate


def generate_sellers(
    n_rows: int,
    geolocations: list[dict[str, Any]],
    categories: list[dict[str, str]],
    fake: Faker,
    rng: random.Random,
    registration_cutoff: date,
) -> list[dict[str, Any]]:
    specific_type_by_group = {
        "tecnologia": "Loja de tecnologia", "casa": "Loja de casa e decoração",
        "moda": "Loja de moda", "automotivo": "Loja automotiva", "beleza": "Loja de beleza",
        "pets": "Loja pet", "livros": "Livraria", "ferramentas": "Loja de ferramentas",
        "bebidas": "Loja de bebidas", "esporte": "Loja de esportes", "infantil": "Loja infantil",
    }
    groups = list(dict.fromkeys(row["grupo"] for row in categories))
    rows: list[dict[str, Any]] = []
    used_names: set[str] = set()
    reg_start = date(2013, 1, 1)
    general_types = ["Distribuidor", "Loja multicanal", "Fabricante"]
    for i in range(1, n_rows + 1):
        geo = rng.choice(geolocations)
        seller_group = groups[(i - 1) % len(groups)]
        specific_type = specific_type_by_group.get(seller_group, "Loja multicanal")
        seller_type = specific_type if rng.random() < 0.72 else rng.choice(general_types)
        name = build_seller_name(rng, seller_type, i, used_names)
        reg_date = random_date(rng, reg_start, registration_cutoff)
        status = weighted_choice(rng, [("ativo", 0.90), ("pausado", 0.07), ("inativo", 0.03)])
        rows.append({
            "seller_id": f"SEL{i:06d}",
            "seller_zip_code_prefix": geo["geolocation_zip_code_prefix"],
            "seller_city": geo["geolocation_city"],
            "seller_state": geo["geolocation_state"],
            "seller_name": name,
            "seller_legal_name": f"{name} Comércio Digital Ltda.",
            "seller_email": f"vendedor{i:06d}@example.com",
            "seller_phone": f"+55 (00) 90000-{i % 10000:04d}",
            "seller_type": seller_type,
            "seller_category_group": seller_group,
            "seller_registration_date": reg_date,
            "seller_status": status,
        })
    return rows


def choose_brand(category_group: str, brands: list[dict[str, str]], rng: random.Random) -> str:
    options = [b["brand_name"] for b in brands if b["grupo"] == category_group]
    if not options:
        options = [b["brand_name"] for b in brands if b["grupo"] == "geral"]
    return rng.choice(options)


def generate_products(
    n_rows: int,
    categories: list[dict[str, str]],
    brands: list[dict[str, str]],
    fake: Faker,
    rng: random.Random,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(1, n_rows + 1):
        cat = rng.choice(categories)
        base_name = rng.choice(cat["nombres_base"].split("|"))
        adjective_options = cat["adjetivos"].split("|")
        adjective = rng.choice(adjective_options)
        if adjective.casefold() in base_name.casefold().split():
            alternatives = [a for a in adjective_options if a.casefold() not in base_name.casefold().split()]
            if alternatives:
                adjective = rng.choice(alternatives)
        product_name = f"{base_name[0].upper()}{base_name[1:]} - modelo {adjective}"
        brand = choose_brand(cat["grupo"], brands, rng)
        price = round(rng.uniform(float(cat["precio_min"]), float(cat["precio_max"])), 2)
        weight = rng.randint(int(cat["peso_min_g"]), int(cat["peso_max_g"]))
        if weight > 15000:
            length = rng.randint(40, 180)
            height = rng.randint(25, 160)
            width = rng.randint(30, 150)
        elif weight > 5000:
            length = rng.randint(20, 100)
            height = rng.randint(10, 90)
            width = rng.randint(15, 90)
        elif weight > 2000:
            length = rng.randint(15, 80)
            height = rng.randint(8, 60)
            width = rng.randint(10, 60)
        else:
            length = rng.randint(5, 70)
            height = rng.randint(2, 60)
            width = rng.randint(5, 60)
        description = (
            f"{product_name}, da marca fictícia {brand}. Produto sintético para testes de integração, "
            "qualidade de dados e análise de comércio eletrônico."
        )
        rows.append({
            "product_id": f"PRD{i:07d}",
            "product_category_name": cat["product_category_name"],
            "product_name_lenght": len(product_name),
            "product_description_lenght": len(description),
            "product_photos_qty": rng.randint(1, 6),
            "product_weight_g": weight,
            "product_length_cm": length,
            "product_height_cm": height,
            "product_width_cm": width,
            "product_name": product_name,
            "product_brand": brand,
            "product_sku": f"SKU-{i:08d}",
            "product_reference_price": f"{price:.2f}",
            "product_description": description,
        })
    return rows


def validate_master_data(
    customers: list[dict[str, Any]],
    sellers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    geolocations: list[dict[str, Any]],
    categories: list[dict[str, str]],
    cfg: dict[str, Any],
) -> list[str]:
    checks: list[str] = []
    def assert_check(condition: bool, ok: str, fail: str) -> None:
        if not condition:
            raise ValueError(f"Validación fallida: {fail}")
        checks.append(f"[OK] {ok}")

    assert_check(len(customers) == int(cfg["N_ORDERS"]), "cantidad de clientes/registros igual a N_ORDERS", "cantidad de clientes distinta de N_ORDERS")
    assert_check(len({r["customer_id"] for r in customers}) == len(customers), "customer_id único", "customer_id duplicado")
    assert_check(len({r["seller_id"] for r in sellers}) == len(sellers), "seller_id único", "seller_id duplicado")
    assert_check(len({r["seller_name"] for r in sellers}) == len(sellers), "nombres comerciales de vendedores únicos", "nombre comercial repetido")
    assert_check(len({r["product_id"] for r in products}) == len(products), "product_id único", "product_id duplicado")
    assert_check(len({r["product_sku"] for r in products}) == len(products), "SKU de productos único", "SKU duplicado")
    assert_check(len({r["geolocation_zip_code_prefix"] for r in geolocations}) == len(geolocations), "prefijos postales únicos en geolocalización", "prefijo postal duplicado")

    geo_prefixes = {r["geolocation_zip_code_prefix"] for r in geolocations}
    assert_check(all(r["customer_zip_code_prefix"] in geo_prefixes for r in customers), "todos los clientes tienen prefijo geográfico existente", "prefijo geográfico de cliente no encontrado")
    assert_check(all(r["seller_zip_code_prefix"] in geo_prefixes for r in sellers), "todos los vendedores tienen prefijo geográfico existente", "prefijo geográfico de vendedor no encontrado")
    cat_names = {r["product_category_name"] for r in categories}
    assert_check(all(r["product_category_name"] in cat_names for r in products), "todas las categorías de producto existen en el catálogo", "categoría de producto no catalogada")
    assert_check(all(len(r["customer_zip_code_prefix"]) == 5 for r in customers), "prefijos postales de cliente conservan cinco caracteres", "prefijo postal de cliente inválido")
    assert_check(all(len(r["seller_zip_code_prefix"]) == 5 for r in sellers), "prefijos postales de vendedor conservan cinco caracteres", "prefijo postal de vendedor inválido")
    return checks


def random_datetime(rng: random.Random, day: date, hour_min: int = 7, hour_max: int = 22) -> datetime:
    return datetime(day.year, day.month, day.day, rng.randint(hour_min, hour_max), rng.randint(0, 59), rng.randint(0, 59))


def fmt_ts(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def money(value: float) -> str:
    return f"{value:.2f}"


def choose_order_status(rng: random.Random) -> str:
    return weighted_choice(rng, [
        ("delivered", 0.83), ("shipped", 0.05), ("canceled", 0.025),
        ("unavailable", 0.005), ("invoiced", 0.02), ("processing", 0.025),
        ("created", 0.01), ("approved", 0.035),
    ])


def generate_review_text(score: int, rng: random.Random) -> tuple[str, str]:
    samples = {
        1: [("Experiência ruim", "O produto chegou com problemas e a experiência ficou abaixo do esperado."),
            ("Não recomendo", "A entrega demorou e o atendimento poderia ter sido melhor."),
            ("Insatisfeito", "O pedido não correspondeu às minhas expectativas.")],
        2: [("Pode melhorar", "O produto é razoável, mas houve alguns problemas com a compra."),
            ("Experiência fraca", "A qualidade ficou abaixo do esperado e o prazo poderia melhorar."),
            ("Pouco satisfeito", "Esperava uma experiência melhor com este pedido.")],
        3: [("Experiência regular", "O produto atende ao básico e a compra ocorreu sem grandes problemas."),
            ("Dentro do esperado", "A experiência foi normal, com alguns pontos que poderiam melhorar."),
            ("Razoável", "Recebi o pedido e considero a qualidade mediana.")],
        4: [("Boa compra", "O produto é bom e o pedido chegou em condições adequadas."),
            ("Gostei", "A experiência foi positiva e o produto corresponde à descrição."),
            ("Recomendo", "Boa qualidade e processo de compra satisfatório.")],
        5: [("Excelente", "Produto de ótima qualidade e experiência de compra excelente."),
            ("Muito satisfeito", "Tudo ocorreu bem e o produto superou minhas expectativas."),
            ("Compra perfeita", "Recebi o pedido corretamente e recomendo a loja.")],
    }
    title, message = rng.choice(samples[score])
    # La mayoría de reseñas tiene texto, pero también existen reseñas sin comentario.
    if rng.random() < 0.12:
        return "", ""
    if rng.random() < 0.18:
        return title, ""
    return title, message


def generate_transactions(
    customers: list[dict[str, Any]],
    sellers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    categories: list[dict[str, str]],
    cfg: dict[str, Any],
    rng: random.Random,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Crea pedidos y sus artículos, pagos y reseñas, reutilizando los datos maestros existentes."""
    if end_date < start_date:
        raise ValueError("END_DATE no puede ser anterior a START_DATE")
    category_translation = {r["product_category_name"]: r["product_category_name_english"] for r in categories}
    category_by_name = {r["product_category_name"]: r for r in categories}
    active_sellers = [s for s in sellers if s.get("seller_status") != "inativo"] or sellers
    sellers_by_group: dict[str, list[dict[str, Any]]] = {}
    for seller in active_sellers:
        sellers_by_group.setdefault(seller.get("seller_category_group", "geral"), []).append(seller)
    review_probability = float(cfg.get("REVIEW_PROBABILITY", 0.90))
    if not 0 <= review_probability <= 1:
        raise ValueError("REVIEW_PROBABILITY debe estar entre 0 y 1")
    max_items = int(cfg.get("MAX_ITEMS_PER_ORDER", 4))
    if max_items < 1 or max_items > 10:
        raise ValueError("MAX_ITEMS_PER_ORDER debe estar entre 1 y 10")

    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    order_summary: dict[str, dict[str, Any]] = {}

    payment_methods = [("credit_card", 0.63), ("boleto", 0.23), ("voucher", 0.08), ("debit_card", 0.06)]
    item_weights = [0.72, 0.18, 0.07, 0.03]
    item_counts = list(range(1, len(item_weights) + 1))
    statuses_with_payment = {"approved", "processing", "invoiced", "shipped", "delivered"}

    date_span = (end_date - start_date).days
    for order_num, customer in enumerate(customers, start=1):
        if order_num == 1 or order_num % 2000 == 0:
            print(f"  Generando pedido {order_num:,}/{len(customers):,}...", flush=True)
        order_id = f"ODR{order_num:010d}"
        purchase_day = start_date + timedelta(days=rng.randint(0, max(0, date_span)))
        purchase_dt = random_datetime(rng, purchase_day)
        status = choose_order_status(rng)
        estimated_dt = datetime.combine(purchase_day + timedelta(days=rng.randint(7, 25)), datetime.min.time())

        approved_dt: datetime | None = None
        carrier_dt: datetime | None = None
        delivered_dt: datetime | None = None
        if status in {"approved", "processing", "invoiced", "shipped", "delivered"}:
            approved_dt = purchase_dt + timedelta(hours=rng.randint(1, 48))
        elif status in {"canceled", "unavailable"} and rng.random() < 0.25:
            approved_dt = purchase_dt + timedelta(hours=rng.randint(1, 24))

        if status in {"shipped", "delivered"}:
            # La fecha de despacho siempre ocurre después de la aprobación.
            if approved_dt is None:
                approved_dt = purchase_dt + timedelta(hours=rng.randint(1, 24))
            carrier_dt = approved_dt + timedelta(hours=rng.randint(8, 72))
        if status == "delivered":
            if carrier_dt is None:
                carrier_dt = purchase_dt + timedelta(days=1)
            delivered_dt = carrier_dt + timedelta(days=rng.randint(1, 18), hours=rng.randint(0, 12))

        order: dict[str, Any] = {
            "order_id": order_id,
            "customer_id": customer["customer_id"],
            "order_status": status,
            "order_purchase_timestamp": fmt_ts(purchase_dt),
            "order_approved_at": fmt_ts(approved_dt),
            "order_delivered_carrier_date": fmt_ts(carrier_dt),
            "order_delivered_customer_date": fmt_ts(delivered_dt),
            "order_estimated_delivery_date": estimated_dt.strftime("%Y-%m-%d %H:%M:%S"),
        }
        orders.append(order)

        selected_item_count = rng.choices(item_counts, weights=item_weights, k=1)[0]
        selected_item_count = min(selected_item_count, max_items)
        order_total_cents = 0

        for item_num in range(1, selected_item_count + 1):
            product = rng.choice(products)
            product_group = category_by_name[product["product_category_name"]]["grupo"]
            compatible_sellers = sellers_by_group.get(product_group, active_sellers)
            seller = rng.choice(compatible_sellers)
            reference_price = float(product["product_reference_price"])
            price = round(reference_price * rng.uniform(0.82, 1.12), 2)
            weight_kg = max(0.1, float(product["product_weight_g"]) / 1000.0)
            same_state = customer["customer_state"] == seller["seller_state"]
            freight = round(4.50 + weight_kg * rng.uniform(0.7, 2.1) + (0 if same_state else rng.uniform(3.0, 10.0)) + rng.uniform(0, 5.0), 2)
            price_cents = int(round(price * 100))
            freight_cents = int(round(freight * 100))
            order_total_cents += price_cents + freight_cents
            shipping_limit_dt = purchase_dt + timedelta(days=rng.randint(1, 5))
            items.append({
                "order_id": order_id,
                "order_item_id": item_num,
                "product_id": product["product_id"],
                "seller_id": seller["seller_id"],
                "shipping_limit_date": fmt_ts(shipping_limit_dt),
                "price": money(price),
                "freight_value": money(freight),
            })

        # Solo pedidos con aprobación/proceso/pago/envío/entrega tienen pagos en esta simulación.
        if status in statuses_with_payment:
            payment_count = 2 if order_total_cents >= 200 and rng.random() < 0.14 else 1
            if payment_count == 1:
                split_cents = [order_total_cents]
            else:
                first_cents = rng.randint(1, order_total_cents - 1)
                split_cents = [first_cents, order_total_cents - first_cents]
            chosen_methods = [weighted_choice(rng, payment_methods) for _ in range(payment_count)]
            for seq, (amount_cents, payment_type) in enumerate(zip(split_cents, chosen_methods), start=1):
                installments = rng.randint(1, 12) if payment_type == "credit_card" else 1
                payments.append({
                    "order_id": order_id,
                    "payment_sequential": seq,
                    "payment_type": payment_type,
                    "payment_installments": installments,
                    "payment_value": money(amount_cents / 100),
                })

        item_total = order_total_cents / 100
        delivery_days = (delivered_dt.date() - purchase_dt.date()).days if delivered_dt else None
        is_late = (delivered_dt.date() > estimated_dt.date()) if delivered_dt else None
        order_summary[order_id] = {
            "order_total_value": money(item_total),
            "order_item_count": selected_item_count,
            "order_customer_unique_id": customer["customer_unique_id"],
            "order_customer_name": customer.get("customer_name", ""),
            "order_customer_state": customer["customer_state"],
            "order_delivery_days": delivery_days if delivery_days is not None else "",
            "order_is_late": int(is_late) if is_late is not None else "",
        }

        if status == "delivered" and delivered_dt and rng.random() < review_probability:
            # Las entregas tardías reciben algo más de probabilidad de puntuación baja.
            if is_late:
                score = rng.choices([1, 2, 3, 4, 5], weights=[0.20, 0.20, 0.24, 0.22, 0.14], k=1)[0]
            else:
                score = rng.choices([1, 2, 3, 4, 5], weights=[0.04, 0.06, 0.15, 0.32, 0.43], k=1)[0]
            title, message = generate_review_text(score, rng)
            review_dt = delivered_dt + timedelta(days=rng.randint(1, 25), hours=rng.randint(0, 23))
            answer_dt = review_dt + timedelta(days=rng.randint(0, 5)) if rng.random() < 0.86 else None
            reviews.append({
                "review_id": f"REV{len(reviews) + 1:010d}",
                "order_id": order_id,
                "review_score": score,
                "review_comment_title": title,
                "review_comment_message": message,
                "review_creation_date": fmt_ts(review_dt),
                "review_answer_timestamp": fmt_ts(answer_dt),
            })

    return orders, items, payments, reviews, order_summary


def validate_transactions(
    orders: list[dict[str, Any]], items: list[dict[str, Any]], payments: list[dict[str, Any]],
    reviews: list[dict[str, Any]], customers: list[dict[str, Any]], sellers: list[dict[str, Any]],
    products: list[dict[str, Any]], summaries: dict[str, dict[str, Any]], cfg: dict[str, Any],
) -> list[str]:
    checks: list[str] = []
    def assert_check(condition: bool, ok: str, fail: str) -> None:
        if not condition:
            raise ValueError(f"Validación transaccional fallida: {fail}")
        checks.append(f"[OK] {ok}")

    order_ids = {r["order_id"] for r in orders}
    customer_ids = {r["customer_id"] for r in customers}
    seller_ids = {r["seller_id"] for r in sellers}
    product_ids = {r["product_id"] for r in products}
    assert_check(len(orders) == int(cfg["N_ORDERS"]), "cantidad de pedidos igual a N_ORDERS", "cantidad de pedidos distinta de N_ORDERS")
    assert_check(len(order_ids) == len(orders), "order_id único", "order_id duplicado")
    assert_check(all(o["customer_id"] in customer_ids for o in orders), "todos los pedidos apuntan a un customer_id existente", "pedido sin cliente válido")
    assert_check(all(i["order_id"] in order_ids for i in items), "todos los artículos apuntan a pedidos existentes", "artículo con order_id inexistente")
    assert_check(all(i["product_id"] in product_ids for i in items), "todos los artículos apuntan a productos existentes", "artículo con product_id inexistente")
    assert_check(all(i["seller_id"] in seller_ids for i in items), "todos los artículos apuntan a vendedores existentes", "artículo con seller_id inexistente")
    seller_by_id = {r["seller_id"]: r for r in sellers}
    product_by_id = {r["product_id"]: r for r in products}
    category_group_by_name = {r["product_category_name"]: r["grupo"] for r in read_csv_rows(CATALOG_DIR / "categorias.csv")}
    seller_group_matches_product = all(
        seller_by_id[i["seller_id"]].get("seller_category_group") == category_group_by_name[product_by_id[i["product_id"]]["product_category_name"]]
        for i in items
    )
    assert_check(seller_group_matches_product, "vendedor compatible con el grupo de la categoría del producto", "vendedor de un grupo incompatible con la categoría del producto")
    assert_check(all(p["order_id"] in order_ids for p in payments), "todos los pagos apuntan a pedidos existentes", "pago con order_id inexistente")
    assert_check(all(r["order_id"] in order_ids for r in reviews), "todas las reseñas apuntan a pedidos existentes", "reseña con order_id inexistente")
    assert_check(len({r["review_id"] for r in reviews}) == len(reviews), "review_id único", "review_id duplicado")
    assert_check(all(1 <= int(r["review_score"]) <= 5 for r in reviews), "puntuaciones de reseñas entre 1 y 5", "puntuación fuera de rango")

    item_counts_by_order: dict[str, int] = {}
    item_cents_by_order: dict[str, int] = {}
    for row in items:
        oid = row["order_id"]
        item_counts_by_order[oid] = item_counts_by_order.get(oid, 0) + 1
        item_cents_by_order[oid] = item_cents_by_order.get(oid, 0) + int(round((float(row["price"]) + float(row["freight_value"])) * 100))
    assert_check(all(item_counts_by_order.get(oid, 0) >= 1 for oid in order_ids), "cada pedido tiene al menos un artículo", "pedido sin artículos")
    assert_check(len({(r["order_id"], r["order_item_id"]) for r in items}) == len(items), "combinación (order_id, order_item_id) única", "línea de artículo duplicada")

    payment_cents_by_order: dict[str, int] = {}
    for row in payments:
        payment_cents_by_order[row["order_id"]] = payment_cents_by_order.get(row["order_id"], 0) + int(round(float(row["payment_value"]) * 100))
    statuses_with_payment = {"approved", "processing", "invoiced", "shipped", "delivered"}
    expected_paid_orders = {o["order_id"] for o in orders if o["order_status"] in statuses_with_payment}
    assert_check(expected_paid_orders == set(payment_cents_by_order), "solo los pedidos con estado de pago elegible tienen registros de pago", "hay pagos faltantes o inesperados")
    assert_check(all(payment_cents_by_order[oid] == item_cents_by_order[oid] for oid in expected_paid_orders), "pagos coinciden al centavo con artículos + envíos por pedido", "total de pago no coincide con el total del pedido")

    order_by_id = {r["order_id"]: r for r in orders}
    delivered_ids = {o["order_id"] for o in orders if o["order_status"] == "delivered"}
    assert_check(all(r["order_id"] in delivered_ids for r in reviews), "las reseñas solo corresponden a pedidos entregados", "reseña vinculada a pedido no entregado")
    assert_check(all(bool(o["order_delivered_customer_date"]) == (o["order_status"] == "delivered") for o in orders), "solo pedidos entregados tienen fecha de entrega efectiva", "fecha efectiva incompatible con el estado")

    order_purchase_dates = {o["order_id"]: datetime.strptime(o["order_purchase_timestamp"], "%Y-%m-%d %H:%M:%S") for o in orders}
    approval_after_purchase = all(
        not o["order_approved_at"] or datetime.strptime(o["order_approved_at"], "%Y-%m-%d %H:%M:%S") >= order_purchase_dates[o["order_id"]]
        for o in orders
    )
    carrier_after_purchase = all(
        not o["order_delivered_carrier_date"] or datetime.strptime(o["order_delivered_carrier_date"], "%Y-%m-%d %H:%M:%S") >= order_purchase_dates[o["order_id"]]
        for o in orders
    )
    delivered_after_purchase = all(
        not o["order_delivered_customer_date"] or datetime.strptime(o["order_delivered_customer_date"], "%Y-%m-%d %H:%M:%S") >= order_purchase_dates[o["order_id"]]
        for o in orders
    )
    carrier_after_approval = all(
        not (o["order_approved_at"] and o["order_delivered_carrier_date"]) or
        datetime.strptime(o["order_delivered_carrier_date"], "%Y-%m-%d %H:%M:%S") >= datetime.strptime(o["order_approved_at"], "%Y-%m-%d %H:%M:%S")
        for o in orders
    )
    delivered_after_carrier = all(
        not (o["order_delivered_carrier_date"] and o["order_delivered_customer_date"]) or
        datetime.strptime(o["order_delivered_customer_date"], "%Y-%m-%d %H:%M:%S") >= datetime.strptime(o["order_delivered_carrier_date"], "%Y-%m-%d %H:%M:%S")
        for o in orders
    )
    assert_check(approval_after_purchase and carrier_after_purchase and delivered_after_purchase, "fechas operativas posteriores o iguales a la compra", "alguna fecha operativa es anterior a la compra")
    assert_check(carrier_after_approval, "despacho posterior a la aprobación", "despacho anterior a la aprobación")
    assert_check(delivered_after_carrier, "entrega posterior al despacho", "entrega anterior al despacho")

    shipping_limits_valid = all(
        datetime.strptime(i["shipping_limit_date"], "%Y-%m-%d %H:%M:%S") >= order_purchase_dates[i["order_id"]]
        for i in items
    )
    assert_check(shipping_limits_valid, "límites de envío posteriores a la compra", "shipping_limit_date anterior a la compra")

    reviews_after_delivery = all(
        datetime.strptime(r["review_creation_date"], "%Y-%m-%d %H:%M:%S") >= datetime.strptime(order_by_id[r["order_id"]]["order_delivered_customer_date"], "%Y-%m-%d %H:%M:%S")
        for r in reviews
    )
    answers_after_review = all(
        not r["review_answer_timestamp"] or datetime.strptime(r["review_answer_timestamp"], "%Y-%m-%d %H:%M:%S") >= datetime.strptime(r["review_creation_date"], "%Y-%m-%d %H:%M:%S")
        for r in reviews
    )
    assert_check(reviews_after_delivery, "reseñas creadas después de la entrega", "reseña anterior a la entrega")
    assert_check(answers_after_review, "respuestas a reseñas posteriores a su creación", "respuesta anterior a la reseña")
    checks.append(f"[INFO] Pedidos con pago: {len(expected_paid_orders):,}; pedidos sin pago simulado: {len(order_ids - expected_paid_orders):,}")
    checks.append(f"[INFO] Pedidos entregados: {len(delivered_ids):,}; reseñas generadas: {len(reviews):,}; líneas de pedido: {len(items):,}; pagos: {len(payments):,}")
    return checks


def main() -> None:
    cfg = read_config()
    seed = int(cfg["SEED"])
    rng = random.Random(seed)
    Faker.seed(seed)
    fake = Faker("pt_BR")
    fake.seed_instance(seed)

    categories, brands, locations = load_catalogs()
    output_dir = BASE_DIR / str(cfg["OUTPUT_DIR"])
    start_date = parse_date(str(cfg.get("START_DATE", "2016-09-04")))
    end_date = parse_date(str(cfg.get("END_DATE", "2018-10-17")))
    if end_date < start_date:
        raise ValueError("END_DATE no puede ser anterior a START_DATE")

    print("Fase 1/3: preparando geolocalizaciones y datos maestros...")
    print("  Generando geolocalizaciones...", flush=True)
    geolocations = generate_geolocation(int(cfg["N_GEOLOCATIONS"]), locations, rng)
    print("  Generando clientes...", flush=True)
    customers = generate_customers(
        int(cfg["N_ORDERS"]), float(cfg.get("REPEAT_CUSTOMER_RATE", 0.05)),
        geolocations, fake, rng, start_date, end_date,
    )
    print("  Generando vendedores...", flush=True)
    sellers = generate_sellers(int(cfg["N_SELLERS"]), geolocations, categories, fake, rng, start_date)
    print("  Generando productos...", flush=True)
    products = generate_products(int(cfg["N_PRODUCTS"]), categories, brands, fake, rng)
    master_checks = validate_master_data(customers, sellers, products, geolocations, categories, cfg)

    print("Fase 2/3: generando pedidos, artículos, pagos y reseñas...")
    orders, items, payments, reviews, order_summary = generate_transactions(
        customers, sellers, products, categories, cfg, rng, start_date, end_date,
    )
    print("Validando relaciones, importes y fechas...", flush=True)
    transaction_checks = validate_transactions(
        orders, items, payments, reviews, customers, sellers, products, order_summary, cfg,
    )

    customers_by_id = {r["customer_id"]: r for r in customers}
    sellers_by_id = {r["seller_id"]: r for r in sellers}
    products_by_id = {r["product_id"]: r for r in products}
    translations = {r["product_category_name"]: r["product_category_name_english"] for r in categories}

    # Única salida: CSV extendidos que conservan las columnas originales y añaden atributos útiles.
    print("Fase 3/3: exportando un único conjunto de archivos CSV...")
    output_dir.mkdir(parents=True, exist_ok=True)

    ext_customers = [dict(r) for r in customers]
    ext_sellers = [dict(r) for r in sellers]
    ext_products = [dict(r) for r in products]
    ext_orders = []
    for o in orders:
        row = dict(o)
        row.update(order_summary[o["order_id"]])
        ext_orders.append(row)

    ext_items = []
    for i in items:
        row = dict(i)
        product = products_by_id[i["product_id"]]
        seller = sellers_by_id[i["seller_id"]]
        row.update({
            "product_name": product["product_name"],
            "product_brand": product["product_brand"],
            "product_category_name_english": translations.get(product["product_category_name"], ""),
            "seller_name": seller["seller_name"],
            "seller_type": seller["seller_type"],
            "line_total_value": money(float(i["price"]) + float(i["freight_value"])),
        })
        ext_items.append(row)

    ext_reviews = []
    for r in reviews:
        row = dict(r)
        score = int(r["review_score"])
        row["review_sentiment_group"] = "negativa" if score <= 2 else ("neutral" if score == 3 else "positiva")
        ext_reviews.append(row)

    # Limpiar solo los CSV que pertenecen a este generador para evitar archivos obsoletos.
    expected_csv_names = {
        "olist_customers_dataset.csv", "olist_sellers_dataset.csv", "olist_products_dataset.csv",
        "olist_geolocation_dataset.csv", "product_category_name_translation.csv",
        "olist_orders_dataset.csv", "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv", "olist_order_reviews_dataset.csv",
    }
    for old_csv in output_dir.glob("*.csv"):
        if old_csv.name not in expected_csv_names:
            old_csv.unlink()

    write_csv(output_dir / "olist_customers_dataset.csv", ext_customers,
              [*ORIGINAL_COLUMNS["customers"], "customer_name", "customer_email", "customer_phone", "customer_since"])
    write_csv(output_dir / "olist_sellers_dataset.csv", ext_sellers,
              [*ORIGINAL_COLUMNS["sellers"], "seller_name", "seller_legal_name", "seller_email", "seller_phone", "seller_type", "seller_category_group", "seller_registration_date", "seller_status"])
    write_csv(output_dir / "olist_products_dataset.csv", ext_products,
              [*ORIGINAL_COLUMNS["products"], "product_name", "product_brand", "product_sku", "product_reference_price", "product_description"])
    write_csv(output_dir / "olist_geolocation_dataset.csv", geolocations, ORIGINAL_COLUMNS["geolocation"])
    write_csv(output_dir / "product_category_name_translation.csv",
              [{"product_category_name": r["product_category_name"], "product_category_name_english": r["product_category_name_english"]} for r in categories],
              ORIGINAL_COLUMNS["translation"])
    write_csv(output_dir / "olist_orders_dataset.csv", ext_orders,
              [*ORIGINAL_COLUMNS["orders"], "order_total_value", "order_item_count", "order_customer_unique_id", "order_customer_name", "order_customer_state", "order_delivery_days", "order_is_late"])
    write_csv(output_dir / "olist_order_items_dataset.csv", ext_items,
              [*ORIGINAL_COLUMNS["items"], "product_name", "product_brand", "product_category_name_english", "seller_name", "seller_type", "line_total_value"])
    write_csv(output_dir / "olist_order_payments_dataset.csv", payments, ORIGINAL_COLUMNS["payments"])
    write_csv(output_dir / "olist_order_reviews_dataset.csv", ext_reviews,
              [*ORIGINAL_COLUMNS["reviews"], "review_sentiment_group"])

    report = [
        "OLIST FAKER — VALIDACIÓN Y PREPARACIÓN CSV",
        f"Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Semilla: {seed}",
        f"Periodo de compra: {start_date.isoformat()} a {end_date.isoformat()}",
        "Formato de salida: CSV únicamente", "", "ARCHIVOS CSV GENERADOS:",
        f"- Clientes: {len(customers):,} filas",
        f"- Vendedores: {len(sellers):,} filas",
        f"- Productos: {len(products):,} filas",
        f"- Geolocalizaciones: {len(geolocations):,} filas",
        f"- Categorías y traducciones: {len(categories):,} filas",
        f"- Pedidos: {len(orders):,} filas",
        f"- Artículos de pedido: {len(items):,} filas",
        f"- Pagos: {len(payments):,} filas",
        f"- Reseñas: {len(reviews):,} filas", "",
        "VALIDACIONES DE DATOS MAESTROS:", *master_checks,
        "", "VALIDACIONES TRANSACCIONALES:", *transaction_checks, "",
        "REGLAS Y LIMITACIONES:",
        "- Los registros son sintéticos; no representan ventas ni contactos reales.",
        "- Cada archivo de salida es CSV UTF-8 con encabezados.",
        "- Los CSV conservan los campos originales e incorporan campos descriptivos seleccionados.",
        "- Los importes de pago coinciden al centavo con los artículos más los envíos de pedidos elegibles.",
        "- Los pedidos cancelados, no disponibles o creados pueden quedar sin pagos por regla simplificada.",
        "- Las coordenadas y prefijos geográficos son aproximados y sintéticos.",
        "- Este generador no exporta Excel ni escribe directamente en una base de datos.",
    ]
    report_path = BASE_DIR / "VALIDACION_CSV.txt"
    report_path.write_text("\n".join(report), encoding="utf-8")

    print("\nGeneración CSV completada correctamente.")
    print(f"Carpeta de datos: {output_dir}")
    print(f"Clientes: {len(customers):,} | Vendedores: {len(sellers):,} | Productos: {len(products):,}")
    print(f"Pedidos: {len(orders):,} | Artículos: {len(items):,} | Pagos: {len(payments):,} | Reseñas: {len(reviews):,}")
    print(f"Informe de validación: {report_path}")
    print("Se generaron únicamente archivos CSV de datos; no se crearon archivos Excel ni cargas a SQL Server.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
