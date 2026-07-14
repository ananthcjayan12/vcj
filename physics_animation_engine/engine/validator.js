const isObject = value => value && typeof value === 'object' && !Array.isArray(value);

function fallback(schema) {
  if (schema.default !== undefined) return structuredClone(schema.default);
  if (schema.type === 'object') return {};
  if (schema.type === 'array') return [];
  if (schema.type === 'string') return '';
  if (schema.type === 'number' || schema.type === 'integer') return schema.minimum ?? 0;
  if (schema.type === 'boolean') return false;
  return null;
}

function validateValue(value, schema, path, warnings) {
  if (!schema) return value;
  if (value === undefined || value === null) return fallback(schema);

  if (schema.type === 'object') {
    if (!isObject(value)) {
      warnings.push(`${path} must be an object; a fallback was used.`);
      return fallback(schema);
    }
    const output = {};
    for (const [key, childSchema] of Object.entries(schema.properties || {})) {
      const childValue = value[key];
      if ((schema.required || []).includes(key) && (childValue === undefined || childValue === null || childValue === '')) {
        warnings.push(`${path}.${key} is required; a fallback was used.`);
      }
      output[key] = validateValue(childValue, childSchema, `${path}.${key}`, warnings);
    }
    if (schema.additionalProperties !== false) {
      for (const [key, extra] of Object.entries(value)) if (!(key in output)) output[key] = extra;
    }
    return output;
  }

  if (schema.type === 'array') {
    if (!Array.isArray(value)) {
      warnings.push(`${path} must be an array; a fallback was used.`);
      return fallback(schema);
    }
    const min = schema.minItems || 0;
    const max = schema.maxItems || Infinity;
    if (value.length < min) warnings.push(`${path} needs at least ${min} items.`);
    if (value.length > max) warnings.push(`${path} was trimmed to ${max} items.`);
    return value.slice(0, max).map((item, index) => validateValue(item, schema.items, `${path}[${index}]`, warnings));
  }

  if (schema.type === 'string') {
    let output = typeof value === 'string' ? value : String(value);
    if (schema.enum && !schema.enum.includes(output)) {
      warnings.push(`${path} has an unsupported value; “${schema.default ?? schema.enum[0]}” was used.`);
      output = schema.default ?? schema.enum[0];
    }
    if (schema.maxLength && output.length > schema.maxLength) {
      warnings.push(`${path} was trimmed to ${schema.maxLength} characters.`);
      output = output.slice(0, schema.maxLength);
    }
    return output;
  }

  if (schema.type === 'number' || schema.type === 'integer') {
    let output = Number(value);
    if (!Number.isFinite(output)) {
      warnings.push(`${path} must be numeric; a fallback was used.`);
      output = Number(fallback(schema));
    }
    if (schema.minimum !== undefined) output = Math.max(schema.minimum, output);
    if (schema.maximum !== undefined) output = Math.min(schema.maximum, output);
    return schema.type === 'integer' ? Math.round(output) : output;
  }

  if (schema.type === 'boolean') return Boolean(value);
  return value;
}

export function validate(params, schema, path = 'params') {
  const warnings = [];
  const value = validateValue(params, schema, path, warnings);
  return { value, warnings };
}

export function validateSpec(spec, registry) {
  if (!isObject(spec) || !Array.isArray(spec.slides)) throw new Error('The spec must contain a slides array.');
  const warnings = [];
  const slides = spec.slides.map((slide, index) => {
    const ModuleClass = registry[slide.scene];
    if (!ModuleClass) throw new Error(`Unknown scene module: ${slide.scene}`);
    const result = validate(slide.params || {}, ModuleClass.getParamSchema(), `slides[${index}].params`);
    warnings.push(...result.warnings);
    return {
      ...slide,
      duration: Math.max(2, Number(slide.duration) || 6),
      narration: typeof slide.narration === 'string' ? slide.narration : '',
      params: { ...result.value, duration: Math.max(2, Number(slide.duration) || 6) }
    };
  });
  return { spec: { ...spec, slides }, warnings };
}
