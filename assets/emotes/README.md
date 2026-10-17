# 头像表情素材

当前采用黑陶瓷与奶油白两套表情，跟随玩家的黑白执子自动切换。

通过内置 imagegen 工具生成，透明 PNG，网页使用 384 × 384 尺寸。文件分别为 `like.png`（点赞）、`angry.png`（生气）、`laugh.png`（大笑）、`cry.png`（哭哭）。

交互：点击自己的棋子头像，展开四个选项；点选立即发送并收起。每个表情展示 2.4 秒，连发独立播放并错位叠加；单侧最多同时显示 6 张，超出移除最早一张。离线可操作黑白双方。

在线通过独立 SSE 表情事件同步；令牌校验、请求去重、每人每秒最多 8 次。表情不推进棋局版本，不续期房间，重连不重播；发送失败提示点击头像重试。满队列时优先保留棋局快照。表情动画尊重减少动态效果设置。

## 生成提示词

### like

Use case: stylized-concept. Asset type: a single cute emote sticker for a warm minimal Gomoku game UI. Subject: one adorable small ivory ceramic Go stone mascot, rounded squishy dumpling body, tiny stubby arms, dark expressive eyes, subtle peach cheeks. Style: premium soft clay toy illustration with crisp readable silhouette, warm cream and celadon green accents, delicate ink brown outlines, soft studio shading. Composition: one complete character centered, square canvas, generous transparent padding around all edges. No text, no lettering, no watermark, no scene or floor, genuinely transparent background. Action: enthusiastic thumbs up with one clearly raised thumb, delighted smiling eyes, a small celadon sparkle.

### angry

Use case: stylized-concept. Asset type: a single cute emote sticker for a warm minimal Gomoku game UI. Subject: one adorable small ivory ceramic Go stone mascot, rounded squishy dumpling body, tiny stubby arms, dark expressive eyes, subtle peach cheeks. Style: premium soft clay toy illustration with crisp readable silhouette, warm cream and celadon green accents, delicate ink brown outlines, soft studio shading. Composition: one complete character centered, square canvas, generous transparent padding around all edges. No text, no lettering, no watermark, no scene or floor, genuinely transparent background. Action: comically angry but still adorable, puffed rosy cheeks, furrowed eyebrows, tiny clenched fists, small terracotta red steam puff.

### laugh

Use case: stylized-concept. Asset type: a single cute emote sticker for a warm minimal Gomoku game UI. Subject: one adorable small ivory ceramic Go stone mascot, rounded squishy dumpling body, tiny stubby arms, dark expressive eyes, subtle peach cheeks. Style: premium soft clay toy illustration with crisp readable silhouette, warm cream and celadon green accents, delicate ink brown outlines, soft studio shading. Composition: one complete character centered, square canvas, generous transparent padding around all edges. No text, no lettering, no watermark, no scene or floor, genuinely transparent background. Action: laughing joyfully with eyes squeezed shut, wide laughing mouth, little hands on tummy, one tiny laughing tear.

### cry

Use case: stylized-concept. Asset type: a single cute emote sticker for a warm minimal Gomoku game UI. Subject: one adorable small ivory ceramic Go stone mascot, rounded squishy dumpling body, tiny stubby arms, dark expressive eyes, subtle peach cheeks. Style: premium soft clay toy illustration with crisp readable silhouette, warm cream and celadon green accents, delicate ink brown outlines, soft studio shading. Composition: one complete character centered, square canvas, generous transparent padding around all edges. No text, no lettering, no watermark, no scene or floor, genuinely transparent background. Action: cute exaggerated crying, big watery eyes and two short blue streams of tears, tiny hands near cheeks, sympathetic pout.

## 黑棋配套表情

通过内置 imagegen 对白棋参考图逐张生成黑棋版本，保留动作、表情、透明底和原有彩色点缀，黑陶瓷主体。`black-like.png`、`black-angry.png`、`black-laugh.png`、`black-cry.png` 均为 384 × 384。

选择面板按当前玩家执子颜色切换；交换先后手后自动更新。发送事件携带服务端确认的发送时颜色，已播放的表情保留原颜色。离线黑白双方同样适用。

### 黑棋版提示词

#### black-like

Use case: identity-preserve. Asset type: cute transparent emote sticker for a Gomoku game. Edit the reference sticker into its BLACK Go stone counterpart. Preserve the exact same pose, expression, proportions, framing, camera, transparent background, soft clay/ceramic toy illustration quality and existing small colored accents. Change all ivory ceramic character surfaces (body, limbs, hands) to deep charcoal-black ceramic, with subtle warm gray rim highlights so the shape remains legible on cream UI. Keep its expression clearly readable: bright warm-gray expressive eye and eyebrow details where needed, rosy peach cheeks, warm mouth interior, same cheerful cute identity. Do not leave ivory body parts. Do not add objects, text, logos, scenery, floor shadows or checkerboard background. One centered complete character, square canvas, clean alpha transparency. Reference action: delighted thumbs up with a small celadon sparkle.

#### black-angry

Use case: identity-preserve. Asset type: cute transparent emote sticker for a Gomoku game. Edit the reference sticker into its BLACK Go stone counterpart. Preserve the exact same pose, expression, proportions, framing, camera, transparent background, soft clay/ceramic toy illustration quality and existing small colored accents. Change all ivory ceramic character surfaces (body, limbs, hands) to deep charcoal-black ceramic, with subtle warm gray rim highlights so the shape remains legible on cream UI. Keep its expression clearly readable: bright warm-gray expressive eye and eyebrow details where needed, rosy peach cheeks, warm mouth interior, same cheerful cute identity. Do not leave ivory body parts. Do not add objects, text, logos, scenery, floor shadows or checkerboard background. One centered complete character, square canvas, clean alpha transparency. Reference action: adorably angry puffed cheeks, clenched fists and small terracotta steam puff.

#### black-laugh

Use case: identity-preserve. Asset type: cute transparent emote sticker for a Gomoku game. Edit the reference sticker into its BLACK Go stone counterpart. Preserve the exact same pose, expression, proportions, framing, camera, transparent background, soft clay/ceramic toy illustration quality and existing small colored accents. Change all ivory ceramic character surfaces (body, limbs, hands) to deep charcoal-black ceramic, with subtle warm gray rim highlights so the shape remains legible on cream UI. Keep its expression clearly readable: bright warm-gray expressive eye and eyebrow details where needed, rosy peach cheeks, warm mouth interior, same cheerful cute identity. Do not leave ivory body parts. Do not add objects, text, logos, scenery, floor shadows or checkerboard background. One centered complete character, square canvas, clean alpha transparency. Reference action: joyful laughing with eyes squeezed shut, hands on tummy and one blue tear.

#### black-cry

Use case: identity-preserve. Asset type: cute transparent emote sticker for a Gomoku game. Edit the reference sticker into its BLACK Go stone counterpart. Preserve the exact same pose, expression, proportions, framing, camera, transparent background, soft clay/ceramic toy illustration quality and existing small colored accents. Change all ivory ceramic character surfaces (body, limbs, hands) to deep charcoal-black ceramic, with subtle warm gray rim highlights so the shape remains legible on cream UI. Keep its expression clearly readable: bright warm-gray expressive eye and eyebrow details where needed, rosy peach cheeks, warm mouth interior, same cheerful cute identity. Do not leave ivory body parts. Do not add objects, text, logos, scenery, floor shadows or checkerboard background. One centered complete character, square canvas, clean alpha transparency. Reference action: watery crying eyes, blue tears, sympathetic pout and the existing celadon bow.
