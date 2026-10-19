# Olist Faker — Generador CSV para pruebas ETL

Este proyecto genera datos sintéticos inspirados en la estructura del dataset público Brazilian E-Commerce de Olist. Los datos no representan ventas, personas, tiendas ni contactos reales.

## Qué produce

Un único conjunto de **nueve archivos CSV** en `salida/csv/`:

- `olist_customers_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_geolocation_dataset.csv`
- `product_category_name_translation.csv`
- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`

Los CSV conservan los campos originales de Olist y añaden atributos seleccionados para enriquecer el proyecto, como nombre y correo ficticio del cliente, nombre comercial del vendedor, marca y nombre descriptivo del producto, importe calculado de la línea, total del pedido e indicador de entrega tardía. No se generan duplicados separados de esquema extendido/compatible.

## Requisitos

Se recomienda Python 3.10 o posterior. Abre una consola dentro de la carpeta del proyecto y ejecuta:

```bash
py -m pip install -r requirements.txt
```

## Ejecutar

```bash
py generar_olist.py
```

La configuración está en `config.json`:

- `N_ORDERS`: cantidad de pedidos y registros de cliente asociados.
- `N_PRODUCTS`: cantidad de productos.
- `N_SELLERS`: cantidad de vendedores.
- `N_GEOLOCATIONS`: cantidad de prefijos geográficos sintéticos.
- `REPEAT_CUSTOMER_RATE`: probabilidad aproximada de reutilizar el perfil de un cliente.
- `REVIEW_PROBABILITY`: probabilidad de reseña para pedidos elegibles.
- `MAX_ITEMS_PER_ORDER`: máximo de artículos por pedido.
- `START_DATE` y `END_DATE`: intervalo de fechas de compra.
- `SEED`: semilla para reproducibilidad con las mismas versiones de las bibliotecas.
- `OUTPUT_DIR`: ubicación de los CSV, por defecto `salida/csv`.

## Validación

Después de ejecutar, se crea `VALIDACION_CSV.txt` con conteos, reglas y controles de integridad referencial, importes y fechas.

## Notas

- Los datos usan portugués brasileño en nombres y descripciones.
- Los nombres, marcas, emails, teléfonos y coordenadas son sintéticos.
- Los importes de pago de pedidos elegibles coinciden con el total de artículos más envío.
- Los estados, las probabilidades y las distribuciones son reglas didácticas y no reproducen exactamente la distribución real de Olist.
- Este proyecto exporta únicamente archivos de datos CSV; no genera Excel ni inserta datos en SQL Server.
