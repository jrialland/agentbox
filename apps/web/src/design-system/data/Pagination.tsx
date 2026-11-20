import { Pagination as MantinePagination } from "@mantine/core";

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  return (
    <MantinePagination
      value={page}
      total={totalPages}
      onChange={onChange}
      size="sm"
      color="phosphor"
      mt="md"
    />
  );
}
