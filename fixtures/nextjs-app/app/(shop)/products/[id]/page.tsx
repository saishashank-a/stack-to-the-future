import { placeOrder } from "../../../actions";

export default async function Product({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <form action={placeOrder}>
      <input type="hidden" name="productId" value={id} />
      <button type="submit">Order</button>
    </form>
  );
}
