-- Load one quarter of the SEC Financial Statement Data Sets into the database `sec`.
-- Tables and columns as the SEC publishes them (see readme.htm). No primary or foreign keys:
-- auto-ontology must discover the links itself (P2 decision, 2026-11-05).
-- Run: docker cp 2026q1/. postgres:/tmp/sec && docker cp load_sec.sql postgres:/tmp/sec/
--      docker exec postgres psql -U postgres -d sec -v ON_ERROR_STOP=1 -f /tmp/sec/load_sec.sql
DROP TABLE IF EXISTS num, pre, tag, sub;

CREATE TABLE sub (
  adsh text, cik bigint, name text, sic int, countryba text, stprba text, cityba text, zipba text,
  bas1 text, bas2 text, baph text, countryma text, stprma text, cityma text, zipma text, mas1 text,
  mas2 text, countryinc text, stprinc text, ein bigint, former text, changed date, afs text,
  wksi boolean, fye text, form text, period date, fy int, fp text, filed date, accepted timestamp,
  prevrpt boolean, detail boolean, instance text, nciks int, aciks text);

CREATE TABLE tag (
  tag text, version text, custom boolean, abstract boolean, datatype text, iord text, crdr text,
  tlabel text, doc text);

CREATE TABLE num (
  adsh text, tag text, version text, ddate date, qtrs int, uom text, segments text, coreg text,
  value numeric(28,4), footnote text);

CREATE TABLE pre (
  adsh text, report int, line int, stmt text, inpth boolean, rfile text, tag text, version text,
  plabel text, negating boolean);

-- CSV mode: the SEC wraps a value in double quotes when it holds a tab (2 lines in 2026q1 num.txt).
-- The files must be in /tmp/sec inside the postgres container (docker cp).
COPY sub FROM '/tmp/sec/sub.txt' WITH (FORMAT csv, DELIMITER E'\t', HEADER true, NULL '');
COPY tag FROM '/tmp/sec/tag.txt' WITH (FORMAT csv, DELIMITER E'\t', HEADER true, NULL '');
COPY num FROM '/tmp/sec/num.txt' WITH (FORMAT csv, DELIMITER E'\t', HEADER true, NULL '');
COPY pre FROM '/tmp/sec/pre.txt' WITH (FORMAT csv, DELIMITER E'\t', HEADER true, NULL '');

SELECT 'sub' t, count(*) FROM sub UNION ALL SELECT 'tag', count(*) FROM tag
UNION ALL SELECT 'num', count(*) FROM num UNION ALL SELECT 'pre', count(*) FROM pre;
