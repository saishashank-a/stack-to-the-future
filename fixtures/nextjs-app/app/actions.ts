"use server";

export async function placeOrder(form: FormData) {
  const productId = form.get("productId");
  await fetch("http://localhost:3000/api/orders", { method: "POST", body: JSON.stringify({ productId }) });
}

export async function cancelOrder(orderId: string) {
  // TODO: cancelling is not built yet
  throw new Error(`cannot cancel ${orderId}`);
}
