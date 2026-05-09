"""Flash / status message helpers."""


def get_flash(params):
    mapping = {
        'saved': '已保存记录',
        'updated': '已更新记录',
        'archived': '已归档记录',
        'unarchived': '已恢复记录',
        'deleted': '已删除记录',
        'batch_archived': '已批量归档所选记录',
        'batch_unarchived': '已批量恢复所选记录',
        'batch_deleted': '已批量删除所选记录',
        'batch_reviewed': '已批量更新复盘状态',
        'batch_grade': '已批量更新结果评级',
        'batch_deal': '已批量更新成交状态',
        'batch_spread': '已批量更新二次传播状态',
        'imported': '已完成批量导入',
    }
    for key, text in mapping.items():
        if params.get(key, [''])[0] == '1':
            return text
    return ''
