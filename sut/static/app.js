// Tiny vanilla client. Kept dependency-free on purpose: the UI under test should
// never be the reason a test is flaky.
const API = "";
const TOKEN_KEY = "shop_token";

export const store = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  set token(v) { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); },
};

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (store.token) headers["Authorization"] = `Bearer ${store.token}`;
  const res = await fetch(API + path, { ...options, headers });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

export const api = {
  login: (username, password) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  products: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
    return request(`/api/products${qs.toString() ? "?" + qs : ""}`);
  },
  cart: () => request("/api/cart"),
  addToCart: (product_id, quantity = 1) =>
    request("/api/cart/items", { method: "POST", body: JSON.stringify({ product_id, quantity }) }),
  removeFromCart: (id) => request(`/api/cart/items/${id}`, { method: "DELETE" }),
  order: () => request("/api/orders", { method: "POST" }),
};

export function mountHeader() {
  const toggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("main-nav");
  toggle?.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  const logout = document.getElementById("logout");
  if (logout) {
    logout.hidden = !store.token;
    logout.addEventListener("click", () => { store.token = null; location.href = "/login"; });
  }
  refreshCartCount();
}

export async function refreshCartCount() {
  const el = document.getElementById("cart-count");
  if (!el || !store.token) return;
  try {
    const cart = await api.cart();
    el.textContent = String(cart.items.reduce((n, i) => n + i.quantity, 0));
  } catch { /* unauthenticated: leave the badge alone */ }
}

export function requireAuth() {
  if (!store.token) { location.href = "/login"; return false; }
  return true;
}
