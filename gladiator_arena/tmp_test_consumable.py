from src.items import Item
from src.player import Player

player = Player('Test', 'Warrior')
item = Item('Health Potion')
item.count = 3
player.inventory.add(item)
print('before', [(i.name, i.count) for i in player.inventory.items], 'count', player.inventory.count('Health Potion'))
res = player.use_item(player.inventory.items[0])
print('result', res)
print('after', [(i.name, i.count) for i in player.inventory.items], 'count', player.inventory.count('Health Potion'))
res = player.use_item(player.inventory.items[0])
print('after2', [(i.name, i.count) for i in player.inventory.items], 'count', player.inventory.count('Health Potion'))
res = player.use_item(player.inventory.items[0])
print('after3', [(i.name, i.count) for i in player.inventory.items], 'count', player.inventory.count('Health Potion'))
