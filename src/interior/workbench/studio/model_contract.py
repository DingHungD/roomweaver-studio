"""UI purpose meanings, shared by catalog matching and native-model inspection."""
LABELS={'dresser':'梳妝台／化妝桌 (dressing table / makeup vanity table)，不是抽屜櫃或衣櫃',
        'vanity':'浴室洗手台／浴櫃 (bathroom washbasin)，不是梳妝台',
        'cabinet':'收納櫃','wardrobe':'衣櫃','bookcase':'書櫃','shoe_cabinet':'鞋櫃',
        'chair':'椅子或凳子','sofa':'沙發','bed':'床','bunk_bed':'上下舖',
        'nightstand':'床頭櫃／床邊小桌','table':'桌子','desk':'書桌'}
FEATURES={
    'dresser':{'worktop':'可使用的梳妝檯面','knee_space':'坐姿使用處有膝腿空間，不能是一整面櫃門','mirror':'梳妝鏡'},
    'chair':{'seat':'可坐的座面','support':'座面下有合理支撐'},
    'sofa':{'seat':'沙發座面','back':'靠背','support':'底座或支腳'},
    'bed':{'sleeping_surface':'可躺臥的床面','support':'床面支撐結構'},
    'bunk_bed':{'two_levels':'兩層床面','access':'上舖可達的梯子','guard':'上層護欄'},
    'desk':{'worktop':'可使用的桌面','knee_space':'可放腿的坐姿操作空間'},
    'table':{'worktop':'可使用的桌面','support':'桌面支撐'},
    'cabinet':{'storage':'可取用的儲物空間或門抽屜','support':'支腳或落地底座'},
    'wardrobe':{'storage':'衣物收納空間','access':'可使用的櫃門或開放衣物取用面'},
    'bookcase':{'shelves':'可放書的層板與取用面'},
    'vanity':{'basin':'洗手盆，不是單純桌面'},
}

def contract(purpose):
    return dict(purpose=purpose,meaning=LABELS.get(purpose,purpose),required_features=FEATURES.get(purpose,{'function':'可辨識此用途的必要功能結構'}))
