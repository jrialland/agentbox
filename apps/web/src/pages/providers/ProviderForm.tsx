import { useState } from "react";

import type { ProviderTestResult } from "../../api/endpoints";
import { useTestProvider } from "../../api/queries";
import { FormField } from "../../design-system/forms/FormField";
import { PasswordInput } from "../../design-system/forms/PasswordInput";
import { Select } from "../../design-system/forms/Select";
import { TextInput } from "../../design-system/forms/TextInput";
import { Button } from "../../design-system/primitives/Button";
import { getHelpEntry } from "../../help/content";
import { HelpTip } from "../../help/HelpTip";
import styles from "../providers.module.css";
import {
  applyProviderPreset,
  type ProviderDraft,
  PROVIDER_PRESETS,
} from "./providerPresets";
import { ProviderTestResultView } from "./ProviderTestResult";

export function ProviderForm({
  value,
  onChange,
  providerId,
  errors,
}: {
  value: ProviderDraft;
  onChange: (value: ProviderDraft) => void;
  providerId?: string;
  errors?: Partial<
    Record<"name" | "kind" | "baseUrl" | "modelsUrl" | "apiKey", string>
  >;
}) {
  const test = useTestProvider();
  const [result, setResult] = useState<ProviderTestResult | null>(null);
  const entry = getHelpEntry("provider.kind");

  function update(patch: Partial<ProviderDraft>) {
    setResult(null);
    onChange({ ...value, ...patch });
  }

  async function onTest() {
    const validUrl = (value: string) => !value || /^https?:\/\/\S+$/i.test(value);
    if (!validUrl(value.baseUrl) || !validUrl(value.modelsUrl)) {
      setResult({
        ok: false,
        latency_ms: 0,
        model_count: null,
        sample_models: [],
        error: { code: "invalid_url", message: "Enter an http/https URL." },
      });
      return;
    }
    setResult(
      await test.mutateAsync({
        kind: value.kind,
        base_url: value.baseUrl,
        models_url: value.modelsUrl,
        api_key: value.apiKey,
        provider_id: providerId,
      }),
    );
  }

  return (
    <>
      <FormField label="Name" required error={errors?.name}>
        <TextInput
          value={value.name}
          onChange={(event) => update({ name: event.currentTarget.value })}
        />
      </FormField>
      <FormField
        label="Kind"
        required
        help={<HelpTip id="provider.kind" />}
      >
        <Select
          aria-label="Kind"
          data={Object.entries(PROVIDER_PRESETS).map(([kind, preset]) => ({
            value: kind,
            label: preset.label,
          }))}
          value={value.kind}
          onChange={(kind) => {
            if (kind) onChange(applyProviderPreset(value, kind));
            setResult(null);
          }}
        />
      </FormField>
      <p className={styles.guidance}>{entry.summary}</p>
      <FormField
        label="Base URL"
        description="Provider API base, including /v1 when required."
        error={errors?.baseUrl}
        help={<HelpTip id="provider.urls" />}
      >
        <TextInput
          aria-label="Base URL"
          value={value.baseUrl}
          onChange={(event) => update({ baseUrl: event.currentTarget.value })}
        />
      </FormField>
      <FormField label="API key" help={<HelpTip id="provider.api-key" />}>
        <PasswordInput
          aria-label="API key"
          placeholder={providerId ? "leave blank to keep" : "sk-..."}
          value={value.apiKey}
          onChange={(event) => update({ apiKey: event.currentTarget.value })}
        />
      </FormField>
      <FormField
        label="Models URL"
        description="Endpoint that returns the model list."
        error={errors?.modelsUrl}
        help={<HelpTip id="provider.models" />}
      >
        <TextInput
          aria-label="Models URL"
          value={value.modelsUrl}
          onChange={(event) => update({ modelsUrl: event.currentTarget.value })}
        />
      </FormField>
      <div className={styles.testRow}>
        <Button variant="light" onClick={onTest} loading={test.isPending}>
          Test connection
        </Button>
        {result && <ProviderTestResultView result={result} />}
      </div>
    </>
  );
}
