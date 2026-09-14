// Real, recurring bug class in this product family: PostgREST caps any
// unbounded .select() at 1000 rows by default. This project has 603 real
// players - safely under the cap for a single gameweek, but
// predictions_and_actuals accumulates one row per player per gameweek (up
// to 603 * 18 ≈ 10,854 across a full season), so an unfiltered query over
// every gameweek needs this. Ported from the sibling EFL-Projections
// repo's own lib/supabasePaginate.ts, which found this bug for real.
export async function fetchAllRows<T>(
  fetchPage: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>
): Promise<T[]> {
  const PAGE_SIZE = 1000;
  const rows: T[] = [];
  let from = 0;
  while (true) {
    const { data, error } = await fetchPage(from, from + PAGE_SIZE - 1);
    if (error) throw new Error(error.message);
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }
  return rows;
}
