const orders: { productId: string }[] = [];

export async function GET() {
  return Response.json(orders);
}

export async function POST(request: Request) {
  const body = await request.json();
  orders.push({ productId: String(body.productId) });
  return Response.json({ ok: true }, { status: 201 });
}
