-- Create a joined table in BigQuery filtered for US-registered patents from patents-public-data.google_patents_research_publications and patents-public-data.patents.publications. The table will include information about the publication number, application number, title, abstract,  inventor, assignee, CPC codes, top 10 keywords, parent applications, and child applications.

CREATE TEMP TABLE sampled_pubs AS
SELECT
  p2.publication_number,
  p2.top_terms,
  p2.title,
  p2.abstract
FROM `patents-public-data.google_patents_research.publications` AS p2;

CREATE OR REPLACE TABLE `patent-comparer.GooglePatentsPublicDataset.merged_patents` AS
SELECT
  p.publication_number,
  a.application_number,
  p.title AS title_en,
  p.abstract AS abstract_en,
  a.inventor_harmonized,
  a.inventor,
  a.assignee_harmonized,
  a.assignee,
  a.cpc,
  a.parent,
  a.child,
  p.top_terms,
  a.country_code,
  a.publication_date
FROM sampled_pubs as p
LEFT JOIN `patents-public-data.patents.publications` a
  ON p.publication_number = a.publication_number
WHERE
  a.country_code = "US" AND a.publication_date > 20251023;

