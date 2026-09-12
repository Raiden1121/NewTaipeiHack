# Homepage analytics design

## Status

Draft for review. This document records the agreed time policy and calculation
contracts before implementation. It does not change collectors, transforms,
analytics code, the backend, or the frontend.

## 1. Objective

Build the analytics layer for `docs/homepage_analysis.md` while preserving the
pipeline boundary:

- collectors fetch and preserve source records;
- transforms normalize source records into curated datasets;
- analytics joins curated datasets and calculates homepage metrics;
- backend/frontend consume published analytics output and do not recalculate
  the formulas per request.

The homepage output has two different time scopes because the current source
coverage is mixed:

1. annual indicators use ROC 110–114 wherever annual source data exists;
2. the 29-district Youth Opportunity Index (YOI) is calculated once from the
   latest available district snapshots.

The latest snapshot is never backfilled into a historical year.

## 2. Agreed time policy

### 2.1 Annual metrics

The default annual window is ROC 110–114 (2021–2025). The analytics layer
loads ROC 109 only when it is needed as the comparison baseline for the ROC
110 YoY value; ROC 109 is not emitted as part of the five-year output.

Annual outputs include, when the source is available:

- city and district youth population;
- youth population share and annual YoY;
- fertility rate;
- youth bureau legal-budget trend;
- budget YoY between consecutive rows with the same budget status;
- settlement execution rate for years with a parseable final settlement;
- annual source coverage and quality metadata.

The current curated budget rows for ROC 112–116 are not automatically the
requested five-year series. The homepage analytics series filters to ROC
110–114 after the missing years are collected. ROC 115–116 proposal rows stay
in the source dataset but are excluded from this annual comparison.

### 2.2 Current snapshot YOI

`current_yoi` uses the latest available snapshot for each snapshot dataset:

- `job_vacancies`;
- `job_vacancy_salaries`;
- `rentals`;
- `house_prices`;
- `bus_stops`;
- `railway_stops`;
- `bike_stops`.

The population anchor for current YOI is the latest complete annual population
within the annual policy window, normally ROC 114. Each component still keeps
its own `source_period`, so a 2026 job snapshot and a 2025 population anchor
are visible as different source periods.

YOI has no historical YoY field until historical district snapshots are
available. This follows the current homepage specification, which explicitly
states that jobs and rentals are single snapshots.

### 2.3 Election events

Elections are event-based rather than annual:

- 2014 / ROC 103;
- 2018 / ROC 107;
- 2022 / ROC 111.

The dataset remains limited to New Taipei T1 city councilors and V1 borough or
village chiefs. T1 and V1 are separate output branches.

- T1 keeps election-district code and name. It is not assigned to one of the
  29 administrative districts.
- V1 uses the source administrative district and can be aggregated by the 29
  districts.
- President, legislator, mayor, and other election types are excluded.

### 2.4 Service coverage

Service points without a verifiable address or coordinate are outside the
service-point population for this metric. They are excluded and counted in
quality metadata; they are not converted to zero coverage and do not block
calculation for the verified points. The current nine-point source therefore
may produce a partial service set after the three usable addresses are
geocoded.

`serviceCoverageRate` still requires village boundaries and village-level
youth population. If no verified service point can be geocoded, the metric is
`unavailable`; if verified points exist but source coverage is partial, the
metric is calculated with `status=partial` and an explicit excluded-point
count.

## 3. Output contract

Add a homepage analytics writer following the existing analytics convention:

- `data/analytics/homepage/all.json`
- `data/quality/analytics_homepage.json`

The published payload is structured as follows:

```json
{
  "metric_id": "homepage",
  "calculation_version": "1",
  "generated_at": "...",
  "time_policy": {
    "annual_years_roc": [110, 111, 112, 113, 114],
    "current_yoi": "latest_available_snapshot",
    "election_years_roc": [103, 107, 111]
  },
  "current_yoi": {
    "population_reference_year_roc": 114,
    "districts": []
  },
  "annual": {
    "population": [],
    "fertility": [],
    "budget_trend": [],
    "budget_execution": []
  },
  "elections": {
    "city_councilor_t1": [],
    "borough_chief_v1": []
  },
  "service_coverage": {
    "value": null,
    "status": "unavailable",
    "blocking_reasons": []
  }
}
```

Every calculated metric or source-derived component includes, where relevant:

- `source_period`;
- `period_type`: `annual`, `election_event`, or `snapshot`;
- `quality_status`: `observed`, `proxy`, `imputed`, `structural_zero`, or
  `unavailable`;
- `source_datasets`;
- `input_row_count` and coverage counts.

The quality artifact contains validation counts, excluded rows, fallback usage,
and unresolved data blockers. It does not replace the published metric value.

## 4. Current YOI calculation

### 4.1 Normalization

All district-level raw components are normalized across the 29 New Taipei
districts:

```text
x_clipped = clip(x, P5, P95)
norm(x) = (x_clipped - min(x_clipped))
          / (max(x_clipped) - min(x_clipped)) * 100
norm_inv(x) = 100 - norm(x)
```

When the clipped maximum equals the clipped minimum, the normalized value is
50 for every district. The calculation must keep the raw value, clipped value,
normalization bounds, and quality status in the quality artifact.

### 4.2 Weighted YOI

```text
YOI = 0.25 * S_job
    + 0.25 * S_salary
    + 0.05 * S_talent
    + 0.25 * S_housing
    + 0.20 * S_transport
```

The 29 district output contains `opportunityIndex` and a retention risk level.
Risk is calculated from the 29 YOI values:

- `low` when YOI is at or above Q3;
- `high` when YOI is at or below Q1;
- `medium` otherwise.

### 4.3 Work opportunity

```text
S_job = 0.50 * norm(vacancies_per_10k_youth)
      + 0.30 * norm(occupation_shannon_index)
      + 0.20 * norm(national_talent_demand_yoy)
```

- Vacancy counts sum `position_count` from district-level vacancy rows only.
- Occupation diversity uses the raw occupation category fields.
- National talent demand YoY is a shared context value because the source is
  national, not district-level. It does not create artificial district
  differences.

### 4.4 Salary level

```text
S_salary = 0.40 * norm(district_salary_median)
         + 0.30 * norm(high_salary_ratio)
         + 0.30 * norm(adjusted_youth_wage)
```

- `salary_midpoint` is used only when both lower and upper salary bounds are
  present. Lower-bound-only records are excluded from midpoint statistics and
  remain visible in quality counts.
- The high-salary threshold is the citywide salary midpoint median multiplied
  by 1.5. Its numerator is district salary-known records above the threshold;
  the denominator follows the homepage formula and is the district total
  vacancy count. Salary coverage is emitted so a low ratio caused by missing
  salary fields is visible.
- Adjusted youth wage uses the official New Taipei 25–29 wage and the house
  price spatial proxy:

  ```text
  price_ratio(d) = median(house_prices[d]) / median(house_prices[city])
  adjusted_wage(d) = city_wage_25_29 * price_ratio(d)
  ```

  The proxy uses the house-price population specified by the homepage document
  and records its actual source period. If the latest official wage year is
  unavailable, the latest available annual wage within the policy window is
  used and marked `proxy` / `latest_available`.

### 4.5 Talent development

```text
S_talent = 0.30 * norm(college_student_density)
         + 0.35 * norm(vt_course_count)
         + 0.35 * norm(training_people_per_10k_youth)
```

- The canonical annual `college_majors` output is used. The county-level
  period file with null districts is not used for 29-district calculation.
- A district with no college-campus rows is a documented structural zero, not
  an unknown value. `S_talent` remains at the specified overall weight 0.05.
- Missing VT course counts use the observed minimum 32 and are marked
  `imputed` with `imputation_method=observed_minimum`.
- Training is county-level and shared across all districts after dividing by
  the city youth population.

### 4.6 Housing burden

```text
S_housing = 0.35 * norm_inv(rent_median)
          + 0.35 * norm_inv(residential_house_price_median)
          + 0.30 * norm_inv(rent_wage_ratio)
```

- Missing rent districts use the 29-district observed minimum and are marked
  `proxy`.
- House price uses residential records. Pingxi may fall back to all available
  house types when no residential-only records exist, as specified by the
  homepage document.
- Missing house-price districts use the residential observed minimum and are
  marked `proxy`.
- `rent_wage_ratio` is district rent median divided by district salary median;
  salary coverage is carried into the quality output.

### 4.7 Transport accessibility

```text
S_transport = 0.35 * norm(bus_stops_per_10k_youth)
            + 0.40 * norm(railway_stop_density)
            + 0.25 * norm(bike_stop_density)
```

- Bus and bike records with no valid New Taipei district mapping are excluded,
  not assigned by guesswork.
- Districts with no railway station receive structural zero for railway count.
- Area denominators come from a validated New Taipei district boundary source
  or a checked canonical area configuration. The analytics module must not
  silently use a frontend fixture without recording the source.

## 5. Annual metric calculation

### 5.1 Population

For ROC 110–114, emit city and district population rows. The ROC 109 source
is loaded only for the ROC 110 comparison. The national youth population keeps
the homepage fallback constant when no national source is available, and the
fallback is marked in quality metadata.

### 5.2 Fertility

For each ROC year and district:

```text
fertility_rate = births_mother_age_18_35
                 / average_monthly_female_population_18_35
                 * 1,000
```

The denominator is the average of the year's available monthly 18–35 female
population values. The data refresh workflow should first attempt to collect
all 12 months; the analytics input resolver only loads curated outputs and
checks their coverage. If a month remains unavailable, the output retains the
available-month count and coverage ratio rather than silently treating the
missing month as zero.

The city rate is calculated from city-level numerator and denominator totals,
not by averaging district rates. `fertilityVsCityAvg` is derived from the same
year's city value.

### 5.3 Youth bureau budget

The annual homepage trend filters `youth_budgets` to:

- `budget_year_roc` in 110–114;
- `row_type=total`;
- legal budget rows for the five-year legal-budget trend.

Proposed-budget rows are not mixed with legal-budget rows. Settlement execution
uses the homepage formula:

```text
execution_rate = realized_amount / legal_budget_amount * 100
```

The `settlement_amount`, payable amount, reserved amount, and surplus amount
remain available as raw settlement fields, but are not substituted for
`realized_amount`. A year with an image-only or otherwise unparseable final
settlement emits `execution_rate=null` and a failure reason.

## 6. Election analytics

The existing youth participation document defines the rate as:

```text
youth_candidacy_rate = candidates_18_35 / youth_population_18_35 * 100000
```

Candidate age is evaluated at the election voting date using birth date or
birth year, with source age retained for audit.

Output grain:

- `city_councilor_t1`: election district grain, including candidate counts and
  source election district code/name. It also includes a citywide aggregate
  where the New Taipei youth population is a valid denominator.
- `borough_chief_v1`: New Taipei 29-district grain, including candidate and
  elected-person breakdowns where the source supports it.

T1 records are not forced into `district_id`; therefore the 29-district YOI
rows must not receive a fabricated T1 value. A frontend adapter can present
the T1 event table or citywide KPI separately from the 29-district map.

## 7. Service coverage status

The current output is deliberately:

```json
{
  "value": null,
  "status": "unavailable",
  "blocking_reasons": [
    "village_boundaries_not_registered",
    "village_youth_population_not_published"
  ],
  "verified_point_count": 0,
  "excluded_point_count": 6
}
```

The planned formula remains the homepage definition: union 2.5 km buffers for
verified points, intersect village polygons in an equal-area CRS, allocate
covered youth by area fraction, and aggregate to the district. The boundary
source should be the official New Taipei village-boundary dataset or the
National Land Surveying and Mapping Center village-boundary data. The boundary
geometry itself supplies the coordinates; an extra village latitude/longitude
column is optional and is not used for area intersection.

The existing `population` transform already receives village rows and keeps
their age fields inside `raw_records`, but its canonical output is district
level. Add a separate curated `population_villages` output rather than making
analytics parse `raw_records`. It must expose at least `village_code`,
`village_name`, `district_id`, `period_start`, `youth_18_35_female`, and
`youth_18_35_total`.

## 8. Input resolution and quality rules

The existing `load_curated_dataset()` behavior is sufficient for an
all-available dataset but not for this cross-period contract. The analytics
implementation adds an explicit input resolver that can:

- select one annual period or a requested annual range;
- select the latest snapshot for snapshot datasets;
- reject a source period outside the requested scope unless it is an explicit
  exception;
- return source-period and row-count metadata alongside records;
- distinguish a dataset with no rows from a dataset whose rows were excluded
  because of scope or geography.

The resolver must use the dataset index and curated paths, not scan raw files
or calculate from collector artifacts.

The service-coverage input set additionally requires:

- `population_villages` for village-level youth denominators;
- `village_boundaries` for polygon geometry and village-code joins;
- only service points with validated coordinates.

## 9. Out of scope for this delivery

- Backfilling historical district job, salary, rental, or transport snapshots
  and calculating five annual YOI values.
- Geocoding the six service points without usable addresses by guessing a
  street address.
- Assigning T1 election districts to a single administrative district.
- Request-time analytics in the backend.
- Changing collector schemas to calculate homepage metrics.

## 10. Acceptance criteria for implementation planning

The subsequent implementation plan must include tests proving that:

1. annual outputs contain ROC 110–114 and do not accidentally include ROC 115
   or 116 in the five-year budget series;
2. current YOI emits exactly 29 district rows and records each input snapshot
   period;
3. P5/P95 clipping, inverse normalization, constant-column behavior, and Q1/Q3
   risk labels match the formula;
4. salary lower-bound-only rows do not become fake midpoint values;
5. VT 32, missing rent, missing house price, college structural zero, and
   transport exclusions are all marked in quality output;
6. fertility uses monthly female-population averages and reports month
   coverage;
7. T1 remains election-district grain and V1 maps to 29 districts;
8. budget execution is null for unparseable settlement years and uses
   `realized_amount` when available;
9. service points without valid coordinates are excluded and reported rather
   than treated as zero coverage;
10. village population output preserves village code/name and 18–35 counts;
11. village-boundary geometry joins population by stable village identifier;
12. service coverage remains null or partial with explicit blocking reasons and
    excluded-point counts;
13. all JSON output is finite, deterministic for fixed inputs, and written
    atomically using the existing analytics I/O conventions.
