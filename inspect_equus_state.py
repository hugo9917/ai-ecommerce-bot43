import json

from bs4 import BeautifulSoup


def main() -> None:
    html = open("_equus.html", "r", encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")
    tmpl = soup.select_one('template[data-varname="__STATE__"] script')
    print("tmpl_found", bool(tmpl))
    if not tmpl:
        return

    state = json.loads(tmpl.get_text())
    prod_keys = [k for k in state.keys() if k.startswith("Product:")]
    print("state_keys", len(state), "product_keys", len(prod_keys))

    # Buscar posibles objetos de búsqueda que referencien productos
    candidates = []
    for k, v in state.items():
        if not isinstance(v, dict):
            continue
        if "products" in v and isinstance(v["products"], list) and v["products"]:
            candidates.append((k, len(v["products"])))
    candidates.sort(key=lambda x: x[1], reverse=True)
    print("candidates_with_products_top5", candidates[:5])
    if candidates:
        k0 = candidates[0][0]
        v0 = state.get(k0)
        if isinstance(v0, dict) and isinstance(v0.get("products"), list) and v0["products"]:
            print("first_search_product", v0["products"][0])
    if not prod_keys:
        return

    first = state[prod_keys[0]]
    print("first_name", first.get("productName"))
    print("first_link", first.get("link"))
    items = first.get("items")
    print("items_type", type(items), "items_len", len(items) if isinstance(items, list) else None)
    pr = first.get("priceRange")
    print("priceRange_field", pr)
    if isinstance(pr, dict) and pr.get("id") and pr.get("id") in state:
        pr_obj = state[pr["id"]]
        print("priceRange_obj_keys", list(pr_obj.keys()))
        print("priceRange_obj", pr_obj)
        sp = pr_obj.get("sellingPrice")
        if isinstance(sp, dict) and sp.get("id") in state:
            sp_obj = state[sp["id"]]
            print("sellingPrice_obj", sp_obj)
        lp = pr_obj.get("listPrice")
        if isinstance(lp, dict) and lp.get("id") in state:
            lp_obj = state[lp["id"]]
            print("listPrice_obj", lp_obj)
    if isinstance(items, list) and items:
        sellers = items[0].get("sellers")
        print("sellers_len", len(sellers) if isinstance(sellers, list) else None)
        if isinstance(sellers, list) and sellers:
            offer = sellers[0].get("commertialOffer")
            if isinstance(offer, dict):
                print("offer_price", offer.get("Price"), "offer_listprice", offer.get("ListPrice"))


if __name__ == "__main__":
    main()

