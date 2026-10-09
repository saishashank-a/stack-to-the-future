const PRODUCTS = [
  { id: "1", name: "Flux capacitor" },
  { id: "2", name: "Hoverboard" },
];

export default function Products() {
  return (
    <ul>
      {PRODUCTS.map((p) => (
        <li key={p.id}>
          <a href={`/products/${p.id}`}>{p.name}</a>
        </li>
      ))}
    </ul>
  );
}
