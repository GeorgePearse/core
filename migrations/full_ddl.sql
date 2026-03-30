--
-- PostgreSQL database dump
--


-- Dumped from database version 15.15 (Debian 15.15-1.pgdg13+1)
-- Dumped by pg_dump version 15.15 (Debian 15.15-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';


--
-- Name: agent_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_actions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    action_type text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: code_lineages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_lineages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    child_id uuid NOT NULL,
    parent_id uuid,
    generation integer NOT NULL,
    mutation_type text NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    fitness_delta double precision DEFAULT 0 NOT NULL,
    edit_summary text DEFAULT ''::text NOT NULL
);


--
-- Name: evolution_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evolution_runs (
    run_id uuid DEFAULT gen_random_uuid() NOT NULL,
    start_time timestamp with time zone DEFAULT now() NOT NULL,
    end_time timestamp with time zone,
    task_name text NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'running'::text NOT NULL,
    total_generations integer DEFAULT 0 NOT NULL,
    population_size integer DEFAULT 0 NOT NULL,
    cluster_type text,
    database_path text
);


--
-- Name: generations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generations (
    run_id uuid NOT NULL,
    generation integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    num_individuals integer DEFAULT 0 NOT NULL,
    best_score double precision DEFAULT 0 NOT NULL,
    avg_score double precision DEFAULT 0 NOT NULL,
    pareto_size integer DEFAULT 0 NOT NULL,
    total_cost double precision DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: individuals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.individuals (
    run_id uuid NOT NULL,
    individual_id uuid DEFAULT gen_random_uuid() NOT NULL,
    generation integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    parent_id uuid,
    mutation_type text NOT NULL,
    fitness_score double precision DEFAULT 0 NOT NULL,
    combined_score double precision DEFAULT 0 NOT NULL,
    metrics jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_pareto boolean DEFAULT false NOT NULL,
    api_cost double precision DEFAULT 0 NOT NULL,
    embed_cost double precision DEFAULT 0 NOT NULL,
    novelty_cost double precision DEFAULT 0 NOT NULL,
    code_hash text DEFAULT ''::text NOT NULL,
    code_size integer DEFAULT 0 NOT NULL,
    code text DEFAULT ''::text NOT NULL,
    language text DEFAULT 'python'::text NOT NULL,
    text_feedback text DEFAULT ''::text NOT NULL,
    correct boolean DEFAULT false NOT NULL
);


--
-- Name: llm_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.llm_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    model text NOT NULL,
    messages jsonb DEFAULT '[]'::jsonb NOT NULL,
    response text DEFAULT ''::text NOT NULL,
    thought text DEFAULT ''::text NOT NULL,
    cost double precision DEFAULT 0 NOT NULL,
    execution_time double precision DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: pareto_fronts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pareto_fronts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    generation integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    individual_id uuid NOT NULL,
    fitness_score double precision DEFAULT 0 NOT NULL,
    combined_score double precision DEFAULT 0 NOT NULL,
    metrics jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: agent_actions agent_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_actions
    ADD CONSTRAINT agent_actions_pkey PRIMARY KEY (id);


--
-- Name: code_lineages code_lineages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_lineages
    ADD CONSTRAINT code_lineages_pkey PRIMARY KEY (id);


--
-- Name: evolution_runs evolution_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evolution_runs
    ADD CONSTRAINT evolution_runs_pkey PRIMARY KEY (run_id);


--
-- Name: generations generations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generations
    ADD CONSTRAINT generations_pkey PRIMARY KEY (run_id, generation);


--
-- Name: individuals individuals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.individuals
    ADD CONSTRAINT individuals_pkey PRIMARY KEY (run_id, individual_id);


--
-- Name: llm_logs llm_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_logs
    ADD CONSTRAINT llm_logs_pkey PRIMARY KEY (id);


--
-- Name: pareto_fronts pareto_fronts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pareto_fronts
    ADD CONSTRAINT pareto_fronts_pkey PRIMARY KEY (id);


--
-- Name: idx_agent_actions_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_actions_timestamp ON public.agent_actions USING btree ("timestamp" DESC);


--
-- Name: idx_agent_actions_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_actions_type ON public.agent_actions USING btree (action_type);


--
-- Name: idx_code_lineages_child; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_lineages_child ON public.code_lineages USING btree (child_id);


--
-- Name: idx_code_lineages_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_lineages_parent ON public.code_lineages USING btree (parent_id);


--
-- Name: idx_code_lineages_run_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_lineages_run_gen ON public.code_lineages USING btree (run_id, generation);


--
-- Name: idx_evolution_runs_start_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evolution_runs_start_time ON public.evolution_runs USING btree (start_time DESC);


--
-- Name: idx_evolution_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evolution_runs_status ON public.evolution_runs USING btree (status);


--
-- Name: idx_evolution_runs_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evolution_runs_task ON public.evolution_runs USING btree (task_name);


--
-- Name: idx_generations_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_generations_run ON public.generations USING btree (run_id);


--
-- Name: idx_individuals_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_individuals_parent ON public.individuals USING btree (parent_id);


--
-- Name: idx_individuals_run_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_individuals_run_gen ON public.individuals USING btree (run_id, generation);


--
-- Name: idx_individuals_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_individuals_score ON public.individuals USING btree (combined_score DESC);


--
-- Name: idx_llm_logs_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_logs_model ON public.llm_logs USING btree (model);


--
-- Name: idx_llm_logs_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_logs_timestamp ON public.llm_logs USING btree ("timestamp" DESC);


--
-- Name: idx_pareto_fronts_run_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pareto_fronts_run_gen ON public.pareto_fronts USING btree (run_id, generation);


--
-- Name: idx_pareto_fronts_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pareto_fronts_score ON public.pareto_fronts USING btree (fitness_score DESC);


--
-- Name: code_lineages code_lineages_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_lineages
    ADD CONSTRAINT code_lineages_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.evolution_runs(run_id) ON DELETE CASCADE;


--
-- Name: generations generations_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generations
    ADD CONSTRAINT generations_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.evolution_runs(run_id) ON DELETE CASCADE;


--
-- Name: individuals individuals_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.individuals
    ADD CONSTRAINT individuals_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.evolution_runs(run_id) ON DELETE CASCADE;


--
-- Name: pareto_fronts pareto_fronts_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pareto_fronts
    ADD CONSTRAINT pareto_fronts_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.evolution_runs(run_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


