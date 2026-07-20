export const normalizeText = (value = '') => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
export const includesNormalized = (source = '', query = '') => normalizeText(source).includes(normalizeText(query));
