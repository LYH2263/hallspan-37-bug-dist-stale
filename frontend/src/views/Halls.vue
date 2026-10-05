<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const edits = ref<Record<number, string>>({})
const errors = ref<Record<number, string>>({})
const saving = ref<Set<number>>(new Set())

onMounted(load)
async function load() {
  rows.value = await api('/halls')
  for (const r of rows.value) edits.value[r.id] = String(r.min_manhattan)
}
function diagonal(r: any) { return (r.rows - 1) + (r.cols - 1) }

async function save(r: any) {
  const v = Number(edits.value[r.id])
  errors.value[r.id] = ''
  if (!Number.isInteger(v) || v < 1 || v > diagonal(r)) {
    errors.value[r.id] = `距离须为 1 ~ ${diagonal(r)}（考室对角线）的整数，已拒绝保存，方案未改动`
    edits.value[r.id] = String(r.min_manhattan)
    return
  }
  saving.value.add(r.id)
  try {
    const updated = await api(`/halls/${r.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ min_manhattan: v }),
    })
    Object.assign(r, updated)
    edits.value[r.id] = String(r.min_manhattan)
  } catch (e: any) {
    errors.value[r.id] = '保存失败，距离与排座图已一并回滚：' + (e?.message || e)
    edits.value[r.id] = String(r.min_manhattan)
  } finally {
    saving.value.delete(r.id)
  }
}
</script>
<template>
  <h1>考室</h1>
  <p class="sub">考室网格与最小曼哈顿间距 · 保存新距离会同步重写当前有效（最新）排座方案，历史方案钉死不变</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>行</th><th>列</th><th>对角线上限</th><th>最小间距</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.rows }}</td><td>{{ r.cols }}</td>
          <td class="muted">{{ diagonal(r) }}</td>
          <td>
            <input
              v-model="edits[r.id]"
              type="number"
              min="1"
              :max="diagonal(r)"
              style="width:84px"
              @keyup.enter="save(r)"
            />
          </td>
          <td>
            <button class="btn" :disabled="saving.has(r.id)" @click="save(r)">
              {{ saving.has(r.id) ? '保存中…' : '保存并重排' }}
            </button>
            <div v-if="errors[r.id]" class="muted" style="color:#c0392b;max-width:280px">{{ errors[r.id] }}</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
