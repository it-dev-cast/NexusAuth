--
-- PostgreSQL database dump
--

\restrict QUiU8B2pIgdQso5RM6YyabQG2S4EkJ8gCE4gtRyoiLf84xhN4dEQXIu1aLptnyd

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: prevent_audit_log_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.prevent_audit_log_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs rows are immutable: % is not permitted on row id %',
                TG_OP, OLD.id;
        END;
        $$;


--
-- Name: prevent_event_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.prevent_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION
                'events rows are immutable: % is not permitted on row id %',
                TG_OP, OLD.id;
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    category character varying(100)
);


--
-- Name: applications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.applications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: applications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.applications_id_seq OWNED BY public.applications.id;


--
-- Name: asset_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.asset_attachments (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    attachment_type character varying(20) NOT NULL,
    reference character varying(500) NOT NULL,
    description character varying(500),
    uploaded_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: asset_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.asset_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asset_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.asset_attachments_id_seq OWNED BY public.asset_attachments.id;


--
-- Name: asset_models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.asset_models (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: asset_models_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.asset_models_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asset_models_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.asset_models_id_seq OWNED BY public.asset_models.id;


--
-- Name: asset_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.asset_tags (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    tag character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: asset_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.asset_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: asset_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.asset_tags_id_seq OWNED BY public.asset_tags.id;


--
-- Name: assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assets (
    id integer NOT NULL,
    asset_tag character varying(100) NOT NULL,
    manufacturer character varying(255) NOT NULL,
    model character varying(255) NOT NULL,
    serial_number character varying(255),
    supplier_id integer NOT NULL,
    status character varying(20) DEFAULT 'registered'::character varying NOT NULL,
    barcode_value character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    purchase_cost numeric(12,2),
    current_value numeric(12,2),
    currency character varying(3)
);


--
-- Name: assets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assets_id_seq OWNED BY public.assets.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    user_id integer,
    action character varying(50) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id character varying(100),
    old_value text,
    new_value text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: auth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_sessions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    refresh_token_hash character varying(255) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone,
    revoked_at timestamp with time zone,
    is_revoked boolean NOT NULL,
    access_token_jti character varying(255),
    ip_address character varying(45),
    user_agent character varying(512)
);


--
-- Name: auth_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_sessions_id_seq OWNED BY public.auth_sessions.id;


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    company_type character varying(20) NOT NULL,
    address character varying(500),
    contact_email character varying(255),
    contact_phone character varying(50),
    config_defaults character varying(1000),
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: companies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.companies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.companies_id_seq OWNED BY public.companies.id;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.departments (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    description text,
    manager_name character varying(255),
    parent_department_id integer
);


--
-- Name: departments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.departments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: departments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.departments_id_seq OWNED BY public.departments.id;


--
-- Name: employee_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_applications (
    employee_id integer NOT NULL,
    application_id integer NOT NULL
);


--
-- Name: employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employees (
    id integer NOT NULL,
    company_id integer NOT NULL,
    user_id integer,
    email character varying(255) NOT NULL,
    job_role character varying(100) NOT NULL,
    department character varying(100),
    cost_center character varying(100),
    status character varying(20) NOT NULL,
    bank_account_number text,
    bank_ifsc text,
    pan_number text,
    aadhaar_number text,
    residence_proof_reference text,
    photo_reference text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    manager_id integer,
    first_name character varying(255) NOT NULL,
    last_name character varying(255) NOT NULL,
    employee_code character varying(50),
    designation character varying(150),
    phone_number text,
    linkedin_url character varying(500),
    address text
);


--
-- Name: employees_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.employees_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: employees_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.employees_id_seq OWNED BY public.employees.id;


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id integer NOT NULL,
    event_type character varying(150) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id character varying(100),
    company_id integer,
    payload text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;


--
-- Name: job_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_roles (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: job_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.job_roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: job_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.job_roles_id_seq OWNED BY public.job_roles.id;


--
-- Name: manufacturers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manufacturers (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: manufacturers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.manufacturers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: manufacturers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.manufacturers_id_seq OWNED BY public.manufacturers.id;


--
-- Name: revoked_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revoked_tokens (
    id integer NOT NULL,
    jti character varying(255) NOT NULL,
    user_id integer NOT NULL,
    token_type character varying(50) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone NOT NULL,
    reason character varying(100)
);


--
-- Name: revoked_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.revoked_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: revoked_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.revoked_tokens_id_seq OWNED BY public.revoked_tokens.id;


--
-- Name: suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suppliers (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    contact_email character varying(255),
    contact_phone character varying(50),
    terms character varying(255),
    category character varying(100),
    status character varying(20) DEFAULT 'onboarded'::character varying NOT NULL,
    rating numeric(3,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: suppliers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.suppliers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: suppliers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.suppliers_id_seq OWNED BY public.suppliers.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(50) DEFAULT 'read_only'::character varying NOT NULL,
    is_active boolean NOT NULL,
    failed_login_attempts integer NOT NULL,
    locked_until timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    full_name character varying(255),
    login_count integer DEFAULT 0 NOT NULL,
    last_login_at timestamp without time zone,
    company_id integer
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: applications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications ALTER COLUMN id SET DEFAULT nextval('public.applications_id_seq'::regclass);


--
-- Name: asset_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_attachments ALTER COLUMN id SET DEFAULT nextval('public.asset_attachments_id_seq'::regclass);


--
-- Name: asset_models id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_models ALTER COLUMN id SET DEFAULT nextval('public.asset_models_id_seq'::regclass);


--
-- Name: asset_tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_tags ALTER COLUMN id SET DEFAULT nextval('public.asset_tags_id_seq'::regclass);


--
-- Name: assets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assets ALTER COLUMN id SET DEFAULT nextval('public.assets_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: auth_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions ALTER COLUMN id SET DEFAULT nextval('public.auth_sessions_id_seq'::regclass);


--
-- Name: companies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies ALTER COLUMN id SET DEFAULT nextval('public.companies_id_seq'::regclass);


--
-- Name: departments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments ALTER COLUMN id SET DEFAULT nextval('public.departments_id_seq'::regclass);


--
-- Name: employees id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees ALTER COLUMN id SET DEFAULT nextval('public.employees_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);


--
-- Name: job_roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_roles ALTER COLUMN id SET DEFAULT nextval('public.job_roles_id_seq'::regclass);


--
-- Name: manufacturers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manufacturers ALTER COLUMN id SET DEFAULT nextval('public.manufacturers_id_seq'::regclass);


--
-- Name: revoked_tokens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revoked_tokens ALTER COLUMN id SET DEFAULT nextval('public.revoked_tokens_id_seq'::regclass);


--
-- Name: suppliers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers ALTER COLUMN id SET DEFAULT nextval('public.suppliers_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: applications applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_pkey PRIMARY KEY (id);


--
-- Name: asset_attachments asset_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_attachments
    ADD CONSTRAINT asset_attachments_pkey PRIMARY KEY (id);


--
-- Name: asset_models asset_models_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_models
    ADD CONSTRAINT asset_models_pkey PRIMARY KEY (id);


--
-- Name: asset_tags asset_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_tags
    ADD CONSTRAINT asset_tags_pkey PRIMARY KEY (id);


--
-- Name: assets assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: auth_sessions auth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (id);


--
-- Name: auth_sessions auth_sessions_refresh_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_refresh_token_hash_key UNIQUE (refresh_token_hash);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: employee_applications employee_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_applications
    ADD CONSTRAINT employee_applications_pkey PRIMARY KEY (employee_id, application_id);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: employees employees_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_user_id_key UNIQUE (user_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: job_roles job_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_roles
    ADD CONSTRAINT job_roles_pkey PRIMARY KEY (id);


--
-- Name: manufacturers manufacturers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manufacturers
    ADD CONSTRAINT manufacturers_pkey PRIMARY KEY (id);


--
-- Name: revoked_tokens revoked_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revoked_tokens
    ADD CONSTRAINT revoked_tokens_pkey PRIMARY KEY (id);


--
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (id);


--
-- Name: asset_tags uq_asset_tags_asset_id_tag; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_tags
    ADD CONSTRAINT uq_asset_tags_asset_id_tag UNIQUE (asset_id, tag);


--
-- Name: employees uq_employees_company_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT uq_employees_company_email UNIQUE (company_id, email);


--
-- Name: employees uq_employees_company_employee_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT uq_employees_company_employee_code UNIQUE (company_id, employee_code);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_applications_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_applications_category ON public.applications USING btree (category);


--
-- Name: ix_applications_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_applications_id ON public.applications USING btree (id);


--
-- Name: ix_applications_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_applications_name ON public.applications USING btree (name);


--
-- Name: ix_asset_attachments_asset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_attachments_asset_id ON public.asset_attachments USING btree (asset_id);


--
-- Name: ix_asset_attachments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_attachments_id ON public.asset_attachments USING btree (id);


--
-- Name: ix_asset_attachments_uploaded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_attachments_uploaded_by ON public.asset_attachments USING btree (uploaded_by);


--
-- Name: ix_asset_models_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_models_id ON public.asset_models USING btree (id);


--
-- Name: ix_asset_models_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_asset_models_name ON public.asset_models USING btree (name);


--
-- Name: ix_asset_tags_asset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_tags_asset_id ON public.asset_tags USING btree (asset_id);


--
-- Name: ix_asset_tags_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_tags_id ON public.asset_tags USING btree (id);


--
-- Name: ix_asset_tags_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_asset_tags_tag ON public.asset_tags USING btree (tag);


--
-- Name: ix_assets_asset_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_assets_asset_tag ON public.assets USING btree (asset_tag);


--
-- Name: ix_assets_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assets_id ON public.assets USING btree (id);


--
-- Name: ix_assets_serial_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assets_serial_number ON public.assets USING btree (serial_number);


--
-- Name: ix_assets_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assets_supplier_id ON public.assets USING btree (supplier_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_audit_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_id ON public.audit_logs USING btree (id);


--
-- Name: ix_audit_logs_resource_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_id ON public.audit_logs USING btree (resource_id);


--
-- Name: ix_audit_logs_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);


--
-- Name: ix_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: ix_auth_sessions_access_token_jti; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_access_token_jti ON public.auth_sessions USING btree (access_token_jti);


--
-- Name: ix_auth_sessions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_id ON public.auth_sessions USING btree (id);


--
-- Name: ix_auth_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_user_id ON public.auth_sessions USING btree (user_id);


--
-- Name: ix_companies_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_companies_id ON public.companies USING btree (id);


--
-- Name: ix_companies_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_companies_name ON public.companies USING btree (name);


--
-- Name: ix_departments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_departments_id ON public.departments USING btree (id);


--
-- Name: ix_departments_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_departments_name ON public.departments USING btree (name);


--
-- Name: ix_departments_parent_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_departments_parent_department_id ON public.departments USING btree (parent_department_id);


--
-- Name: ix_employees_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_employees_company_id ON public.employees USING btree (company_id);


--
-- Name: ix_employees_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_employees_email ON public.employees USING btree (email);


--
-- Name: ix_employees_employee_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_employees_employee_code ON public.employees USING btree (employee_code);


--
-- Name: ix_employees_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_employees_id ON public.employees USING btree (id);


--
-- Name: ix_employees_manager_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_employees_manager_id ON public.employees USING btree (manager_id);


--
-- Name: ix_events_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_company_id ON public.events USING btree (company_id);


--
-- Name: ix_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_created_at ON public.events USING btree (created_at);


--
-- Name: ix_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_event_type ON public.events USING btree (event_type);


--
-- Name: ix_events_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_id ON public.events USING btree (id);


--
-- Name: ix_events_resource_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_resource_id ON public.events USING btree (resource_id);


--
-- Name: ix_events_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_resource_type ON public.events USING btree (resource_type);


--
-- Name: ix_job_roles_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_roles_id ON public.job_roles USING btree (id);


--
-- Name: ix_job_roles_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_job_roles_name ON public.job_roles USING btree (name);


--
-- Name: ix_manufacturers_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_manufacturers_id ON public.manufacturers USING btree (id);


--
-- Name: ix_manufacturers_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_manufacturers_name ON public.manufacturers USING btree (name);


--
-- Name: ix_revoked_tokens_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_revoked_tokens_id ON public.revoked_tokens USING btree (id);


--
-- Name: ix_revoked_tokens_jti; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_revoked_tokens_jti ON public.revoked_tokens USING btree (jti);


--
-- Name: ix_revoked_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_revoked_tokens_user_id ON public.revoked_tokens USING btree (user_id);


--
-- Name: ix_suppliers_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_suppliers_id ON public.suppliers USING btree (id);


--
-- Name: ix_suppliers_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_suppliers_name ON public.suppliers USING btree (name);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: audit_logs audit_logs_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_logs_immutable BEFORE DELETE OR UPDATE ON public.audit_logs FOR EACH ROW EXECUTE FUNCTION public.prevent_audit_log_mutation();


--
-- Name: events events_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER events_immutable BEFORE DELETE OR UPDATE ON public.events FOR EACH ROW EXECUTE FUNCTION public.prevent_event_mutation();


--
-- Name: asset_attachments asset_attachments_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_attachments
    ADD CONSTRAINT asset_attachments_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(id) ON DELETE CASCADE;


--
-- Name: asset_attachments asset_attachments_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_attachments
    ADD CONSTRAINT asset_attachments_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: asset_tags asset_tags_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.asset_tags
    ADD CONSTRAINT asset_tags_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(id) ON DELETE CASCADE;


--
-- Name: assets assets_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE RESTRICT;


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: auth_sessions auth_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: employee_applications employee_applications_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_applications
    ADD CONSTRAINT employee_applications_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;


--
-- Name: employee_applications employee_applications_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_applications
    ADD CONSTRAINT employee_applications_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: employees employees_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;


--
-- Name: employees employees_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: events events_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: departments fk_departments_parent_department_id_departments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT fk_departments_parent_department_id_departments FOREIGN KEY (parent_department_id) REFERENCES public.departments(id) ON DELETE SET NULL;


--
-- Name: employees fk_employees_manager_id_employees; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT fk_employees_manager_id_employees FOREIGN KEY (manager_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: users fk_users_company_id_companies; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_company_id_companies FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;


--
-- Name: revoked_tokens revoked_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revoked_tokens
    ADD CONSTRAINT revoked_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict QUiU8B2pIgdQso5RM6YyabQG2S4EkJ8gCE4gtRyoiLf84xhN4dEQXIu1aLptnyd

