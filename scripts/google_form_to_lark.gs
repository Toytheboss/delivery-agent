/**
 * Google Form → Lark Base 自动同步（工作流第 7 步）
 *
 * 用法：
 * 1. 打开 Google 表单 → 回复 → 关联电子表格（如还没有）
 * 2. 打开该电子表格 → 扩展程序 → Apps Script
 * 3. 粘贴本脚本全部内容
 * 4. 在「项目设置 → 脚本属性」添加：
 *      LARK_APP_ID
 *      LARK_APP_SECRET
 *      LARK_APP_TOKEN   （多维表格 app_token）
 *      LARK_TABLE_ID    （目标表 table_id）
 * 5. 按表单实际问题标题，核对 FIELD_MAP 左侧 key 是否一致
 * 6. 触发器：事件来源选「从表单」、事件类型「表单提交时」→ 运行 onFormSubmit
 * 7. 首次手动运行 authorizeLark 完成授权（注意：不要用结尾带 _ 的函数名，下拉列表里看不到）
 *
 * 目标表：项目方钱包地址搜集 (tblj0FdKPrlc7PrM)
 */

var LARK_API = 'https://open.larksuite.com/open-apis';
// 在脚本属性或此处填写目标多维表格（勿把真实 token 提交到公开仓库）
var APP_TOKEN = PropertiesService.getScriptProperties().getProperty('LARK_APP_TOKEN') || 'YOUR_BITABLE_APP_TOKEN';
var TABLE_ID = PropertiesService.getScriptProperties().getProperty('LARK_TABLE_ID') || 'YOUR_TABLE_ID';

// Google 表单「问题标题」→ Lark 字段名（已按 Form_Responses 表头对齐）
var FIELD_MAP = {
  'Project Name': 'Project name',
  'Project name': 'Project name',
  'Project logo': 'Project logo',
  'Mainnet Contract Address': 'Contract Addresss/主网合约',
  'Contract Addresss/主网合约': 'Contract Addresss/主网合约',
  'Treasury Address': 'Treasury Address',
  'Fee Collector / Revenue Wallet Address': 'Fee Collector / Revenue Wallet Address',
  'Multi-sig Threshold (Optional)': 'Multi-sig Threshold (Optional)',
  'Grant Receiving Wallet (Optional)': 'Grant Receiving Wallet (Optional)',
  'MM / LP Wallet (Optional)': 'MM / LP Wallet （Optional）',
  'MM / LP Wallet （Optional）': 'MM / LP Wallet （Optional）',
  'Bridge Pool / Relayer Wallet (Optional)': 'Bridge Pool / Relayer Wallet (Optional)'
};

function authorizeLark() {
  getTenantToken_();
  Logger.log('Lark auth OK');
}

function onFormSubmit(e) {
  var named = (e && e.namedValues) ? e.namedValues : {};
  var fields = {};
  var unmapped = [];

  Object.keys(named).forEach(function (q) {
    var title = String(q || '').trim();
    // Google 有时带尾随空格/换行
    var larkField = FIELD_MAP[title] || FIELD_MAP[title.replace(/\s+/g, ' ')];
    if (!larkField) {
      // 忽略时间戳类系统列
      if (/timestamp|时间戳|电子邮件地址|email/i.test(title)) return;
      unmapped.push(title);
      return;
    }
    var vals = named[q] || [];
    var text = vals.filter(Boolean).join(', ').trim();
    if (text) fields[larkField] = text;
  });

  if (unmapped.length) {
    Logger.log('Unmapped form questions (add to FIELD_MAP if needed): ' + JSON.stringify(unmapped));
  }

  if (!fields['Project name']) {
    throw new Error('Missing Project name in form submission. Questions=' + JSON.stringify(Object.keys(named)));
  }

  var token = getTenantToken_();
  var existing = findByProjectName_(token, fields['Project name']);
  if (existing) {
    updateRecord_(token, existing, fields);
    Logger.log('Updated Lark wallet row ' + existing + ' for ' + fields['Project name']);
  } else {
    var rid = createRecord_(token, fields);
    Logger.log('Created Lark wallet row ' + rid + ' for ' + fields['Project name']);
  }
}

function getTenantToken_() {
  var props = PropertiesService.getScriptProperties();
  var appId = props.getProperty('LARK_APP_ID');
  var appSecret = props.getProperty('LARK_APP_SECRET');
  if (!appId || !appSecret) {
    throw new Error('Set script properties LARK_APP_ID and LARK_APP_SECRET');
  }
  var resp = UrlFetchApp.fetch(LARK_API + '/auth/v3/tenant_access_token/internal', {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ app_id: appId, app_secret: appSecret }),
    muteHttpExceptions: true
  });
  var data = JSON.parse(resp.getContentText());
  if (data.code !== 0) {
    throw new Error('Lark token failed: ' + resp.getContentText());
  }
  return data.tenant_access_token;
}

function listRecords_(token) {
  var items = [];
  var pageToken = '';
  while (true) {
    var url = LARK_API + '/bitable/v1/apps/' + APP_TOKEN + '/tables/' + TABLE_ID +
      '/records?page_size=500' + (pageToken ? ('&page_token=' + encodeURIComponent(pageToken)) : '');
    var resp = UrlFetchApp.fetch(url, {
      method: 'get',
      headers: { Authorization: 'Bearer ' + token },
      muteHttpExceptions: true
    });
    var data = JSON.parse(resp.getContentText());
    if (data.code !== 0) throw new Error('list records failed: ' + resp.getContentText());
    items = items.concat((data.data && data.data.items) || []);
    if (!data.data || !data.data.has_more) break;
    pageToken = data.data.page_token || '';
    if (!pageToken) break;
  }
  return items;
}

function findByProjectName_(token, projectName) {
  var target = String(projectName || '').trim().toLowerCase();
  var items = listRecords_(token);
  for (var i = 0; i < items.length; i++) {
    var name = ((items[i].fields || {})['Project name'] || '');
    if (String(name).trim().toLowerCase() === target) {
      return items[i].record_id;
    }
  }
  return null;
}

function createRecord_(token, fields) {
  var resp = UrlFetchApp.fetch(
    LARK_API + '/bitable/v1/apps/' + APP_TOKEN + '/tables/' + TABLE_ID + '/records',
    {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify({ fields: fields }),
      muteHttpExceptions: true
    }
  );
  var data = JSON.parse(resp.getContentText());
  if (data.code !== 0) throw new Error('create failed: ' + resp.getContentText());
  return data.data.record.record_id;
}

function updateRecord_(token, recordId, fields) {
  var resp = UrlFetchApp.fetch(
    LARK_API + '/bitable/v1/apps/' + APP_TOKEN + '/tables/' + TABLE_ID + '/records/' + recordId,
    {
      method: 'put',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify({ fields: fields }),
      muteHttpExceptions: true
    }
  );
  var data = JSON.parse(resp.getContentText());
  if (data.code !== 0) throw new Error('update failed: ' + resp.getContentText());
}
