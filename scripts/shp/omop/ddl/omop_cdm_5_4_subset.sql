-- OMOP CDM v5.4 — focused subset for the phase-2 estimator stack (DuckDB dialect).
--
-- This is NOT the full 39-table CDM. It is the clinical-event + vocabulary spine
-- the estimator stack actually reads: person-level demographics, observation
-- periods, visits, conditions, drugs, measurements, death — plus the vocabulary
-- tables and the cohort tables OHDSI tools expect. Columns follow the official
-- v5.4 specification names/types so a record loaded here is portable to a full
-- CDM instance (Athena vocab, ETL-Synthea, DQD, Achilles) unchanged.
--
-- Types are simplified to DuckDB-native (BIGINT/VARCHAR/DATE/TIMESTAMP/DOUBLE).

------------------------------------------------------------------- VOCABULARY ---
CREATE TABLE IF NOT EXISTS concept (
    concept_id        BIGINT      PRIMARY KEY,
    concept_name      VARCHAR     NOT NULL,
    domain_id         VARCHAR     NOT NULL,
    vocabulary_id     VARCHAR     NOT NULL,
    concept_class_id  VARCHAR     NOT NULL,
    standard_concept  VARCHAR,                 -- 'S' standard, 'C' classification, NULL non-standard
    concept_code      VARCHAR     NOT NULL,
    valid_start_date  DATE,
    valid_end_date    DATE,
    invalid_reason    VARCHAR
);

CREATE TABLE IF NOT EXISTS vocabulary (
    vocabulary_id          VARCHAR  PRIMARY KEY,
    vocabulary_name        VARCHAR  NOT NULL,
    vocabulary_reference   VARCHAR,
    vocabulary_version     VARCHAR,
    vocabulary_concept_id  BIGINT   NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_relationship (
    concept_id_1      BIGINT   NOT NULL,
    concept_id_2      BIGINT   NOT NULL,
    relationship_id   VARCHAR  NOT NULL,        -- e.g. 'Maps to'
    valid_start_date  DATE,
    valid_end_date    DATE,
    invalid_reason    VARCHAR
);

----------------------------------------------------------------- CDM_SOURCE ---
CREATE TABLE IF NOT EXISTS cdm_source (
    cdm_source_name                 VARCHAR NOT NULL,
    cdm_source_abbreviation         VARCHAR,
    cdm_holder                      VARCHAR,
    source_description              VARCHAR,
    source_documentation_reference  VARCHAR,
    cdm_etl_reference               VARCHAR,
    source_release_date             DATE,
    cdm_release_date                DATE,
    cdm_version                     VARCHAR,
    cdm_version_concept_id          BIGINT,
    vocabulary_version              VARCHAR
);

--------------------------------------------------------------------- PERSON ---
CREATE TABLE IF NOT EXISTS person (
    person_id                     BIGINT  PRIMARY KEY,
    gender_concept_id             BIGINT  NOT NULL,
    year_of_birth                 BIGINT  NOT NULL,
    month_of_birth                BIGINT,
    day_of_birth                  BIGINT,
    birth_datetime                TIMESTAMP,
    race_concept_id               BIGINT  NOT NULL,
    ethnicity_concept_id          BIGINT  NOT NULL,
    location_id                   BIGINT,
    provider_id                   BIGINT,
    care_site_id                  BIGINT,
    person_source_value           VARCHAR,
    gender_source_value           VARCHAR,
    gender_source_concept_id      BIGINT,
    race_source_value             VARCHAR,
    race_source_concept_id        BIGINT,
    ethnicity_source_value        VARCHAR,
    ethnicity_source_concept_id   BIGINT
);

--------------------------------------------------------- OBSERVATION_PERIOD ---
CREATE TABLE IF NOT EXISTS observation_period (
    observation_period_id          BIGINT  PRIMARY KEY,
    person_id                      BIGINT  NOT NULL,
    observation_period_start_date  DATE    NOT NULL,
    observation_period_end_date    DATE    NOT NULL,
    period_type_concept_id         BIGINT  NOT NULL
);

----------------------------------------------------------- VISIT_OCCURRENCE ---
CREATE TABLE IF NOT EXISTS visit_occurrence (
    visit_occurrence_id           BIGINT  PRIMARY KEY,
    person_id                     BIGINT  NOT NULL,
    visit_concept_id              BIGINT  NOT NULL,
    visit_start_date              DATE    NOT NULL,
    visit_start_datetime          TIMESTAMP,
    visit_end_date                DATE    NOT NULL,
    visit_end_datetime            TIMESTAMP,
    visit_type_concept_id         BIGINT  NOT NULL,
    provider_id                   BIGINT,
    care_site_id                  BIGINT,
    visit_source_value            VARCHAR,
    visit_source_concept_id       BIGINT
);

------------------------------------------------------- CONDITION_OCCURRENCE ---
CREATE TABLE IF NOT EXISTS condition_occurrence (
    condition_occurrence_id        BIGINT  PRIMARY KEY,
    person_id                      BIGINT  NOT NULL,
    condition_concept_id           BIGINT  NOT NULL,
    condition_start_date           DATE    NOT NULL,
    condition_start_datetime       TIMESTAMP,
    condition_end_date             DATE,
    condition_end_datetime         TIMESTAMP,
    condition_type_concept_id      BIGINT  NOT NULL,
    condition_status_concept_id    BIGINT,
    stop_reason                    VARCHAR,
    provider_id                    BIGINT,
    visit_occurrence_id            BIGINT,
    visit_detail_id                BIGINT,
    condition_source_value         VARCHAR,
    condition_source_concept_id    BIGINT,
    condition_status_source_value  VARCHAR
);

------------------------------------------------------------- DRUG_EXPOSURE ---
CREATE TABLE IF NOT EXISTS drug_exposure (
    drug_exposure_id              BIGINT  PRIMARY KEY,
    person_id                     BIGINT  NOT NULL,
    drug_concept_id               BIGINT  NOT NULL,
    drug_exposure_start_date      DATE    NOT NULL,
    drug_exposure_start_datetime  TIMESTAMP,
    drug_exposure_end_date        DATE,
    drug_exposure_end_datetime    TIMESTAMP,
    verbatim_end_date             DATE,
    drug_type_concept_id          BIGINT  NOT NULL,
    stop_reason                   VARCHAR,
    refills                       BIGINT,
    quantity                      DOUBLE,
    days_supply                   BIGINT,
    sig                           VARCHAR,
    route_concept_id              BIGINT,
    lot_number                    VARCHAR,
    provider_id                   BIGINT,
    visit_occurrence_id           BIGINT,
    visit_detail_id               BIGINT,
    drug_source_value             VARCHAR,
    drug_source_concept_id        BIGINT,
    route_source_value            VARCHAR,
    dose_unit_source_value        VARCHAR
);

--------------------------------------------------------------- MEASUREMENT ---
CREATE TABLE IF NOT EXISTS measurement (
    measurement_id                BIGINT  PRIMARY KEY,
    person_id                     BIGINT  NOT NULL,
    measurement_concept_id        BIGINT  NOT NULL,
    measurement_date              DATE    NOT NULL,
    measurement_datetime          TIMESTAMP,
    measurement_time              VARCHAR,
    measurement_type_concept_id   BIGINT  NOT NULL,
    operator_concept_id           BIGINT,
    value_as_number               DOUBLE,
    value_as_concept_id           BIGINT,
    unit_concept_id               BIGINT,
    range_low                     DOUBLE,
    range_high                    DOUBLE,
    provider_id                   BIGINT,
    visit_occurrence_id           BIGINT,
    visit_detail_id               BIGINT,
    measurement_source_value      VARCHAR,
    measurement_source_concept_id BIGINT,
    unit_source_value             VARCHAR,
    value_source_value            VARCHAR
);

---------------------------------------------------------------------- DEATH ---
CREATE TABLE IF NOT EXISTS death (
    person_id               BIGINT  NOT NULL,
    death_date              DATE    NOT NULL,
    death_datetime          TIMESTAMP,
    death_type_concept_id   BIGINT,
    cause_concept_id        BIGINT,
    cause_source_value      VARCHAR,
    cause_source_concept_id BIGINT
);

------------------------------------------------------------------- COHORTS ---
-- OHDSI cohort tables (CohortMethod / target-trial emulation read these).
CREATE TABLE IF NOT EXISTS cohort_definition (
    cohort_definition_id           BIGINT  NOT NULL,
    cohort_definition_name         VARCHAR NOT NULL,
    cohort_definition_description  VARCHAR,
    definition_type_concept_id     BIGINT,
    cohort_definition_syntax       VARCHAR,
    subject_concept_id             BIGINT,
    cohort_initiation_date         DATE
);

CREATE TABLE IF NOT EXISTS cohort (
    cohort_definition_id  BIGINT  NOT NULL,
    subject_id            BIGINT  NOT NULL,
    cohort_start_date     DATE    NOT NULL,
    cohort_end_date       DATE    NOT NULL
);
